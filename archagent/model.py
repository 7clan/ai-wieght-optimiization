"""Model access for the autonomous development harness.

Frozen Qwen2.5-Coder-0.5B on CPU.  No gradients, no training, no adapters.
The model directory is resolved from ARCHAGENT_MODEL_DIR (required; no
machine-specific default — Session 011 audit discipline).  The
architecture is verified on load so a wrong directory fails loudly.

Every generation is seeded, timed and token-counted; the caller records
these with the candidate for cost accounting.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B"
EXPECTED_PARAM_COUNT = 494_032_768
EXPECTED_LAYERS = 24
EXPECTED_HIDDEN = 896

FIM_PREFIX = "<|fim_prefix|>"
FIM_SUFFIX = "<|fim_suffix|>"
FIM_MIDDLE = "<|fim_middle|>"


def resolve_model_dir() -> str:
    path = os.environ.get("ARCHAGENT_MODEL_DIR", "")
    if not path:
        raise RuntimeError(
            "ARCHAGENT_MODEL_DIR is not set.  Point it at a local copy of "
            f"'{BASE_MODEL_ID}' and retry.")
    if not Path(path).is_dir():
        raise RuntimeError(f"ARCHAGENT_MODEL_DIR={path!r} is not a directory")
    return path


class FrozenModel:
    """Holds the loaded model + tokenizer; provides generation helpers."""

    def __init__(self, model_dir: str | None = None, threads: int = 2):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        torch.set_num_threads(threads)
        path = model_dir or resolve_model_dir()
        self.model_dir = path
        torch.manual_seed(0)
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForCausalLM.from_pretrained(
            path, dtype=torch.float32).eval().to("cpu")
        n_params = sum(p.numel() for p in self.model.parameters())
        if (n_params != EXPECTED_PARAM_COUNT
                or len(self.model.model.layers) != EXPECTED_LAYERS
                or self.model.config.hidden_size != EXPECTED_HIDDEN):
            raise ValueError(
                "Not the fixed Qwen2.5-Coder-0.5B architecture "
                f"(params={n_params})")
        self.model.requires_grad_(False)
        self.total_tokens = 0
        self.total_seconds = 0.0
        self.n_generations = 0

    # -- helpers ----------------------------------------------------------

    def _generate_ids(self, text: str, max_new_tokens: int, seed: int,
                      stochastic: bool):
        torch = self.torch
        torch.manual_seed(seed)
        inputs = self.tokenizer(text, return_tensors="pt",
                                add_special_tokens=False)
        kwargs = {"max_new_tokens": max_new_tokens,
                  "do_sample": stochastic,
                  "pad_token_id": self.tokenizer.eos_token_id}
        if stochastic:
            kwargs.update({"temperature": 0.72, "top_p": 0.93})
        t0 = time.time()
        with torch.inference_mode():
            out = self.model.generate(**inputs, **kwargs)
        dt = time.time() - t0
        n_new = int(out.shape[1] - inputs["input_ids"].shape[1])
        self.total_tokens += n_new
        self.total_seconds += dt
        self.n_generations += 1
        text_out = self.tokenizer.decode(out[0, inputs["input_ids"].shape[1]:],
                                         skip_special_tokens=True)
        return text_out, n_new, dt

    def generate(self, prompt: str, *, max_tokens: int = 512, seed: int = 0,
                 stochastic: bool = False) -> tuple[str, dict]:
        """Plain completion.  Returns (text, usage{tokens, seconds, seed})."""
        text, n, dt = self._generate_ids(prompt, max_tokens, seed, stochastic)
        return text, {"tokens": n, "seconds": round(dt, 2), "seed": seed,
                      "stochastic": stochastic}

    def fim(self, prefix: str, suffix: str, *, instructions: str = "",
            max_tokens: int = 256, seed: int = 0,
            stochastic: bool = False) -> tuple[str, dict]:
        """Native fill-in-the-middle.  Repair instructions sit at the END of
        the prefix region, immediately adjacent to the gap (measured to make
        the model rewrite the broken region instead of copying it)."""
        text = (FIM_PREFIX + prefix + instructions + FIM_SUFFIX + suffix
                + FIM_MIDDLE)
        out, n, dt = self._generate_ids(text, max_tokens, seed, stochastic)
        return out, {"tokens": n, "seconds": round(dt, 2), "seed": seed,
                     "stochastic": stochastic, "fim": True}

    def usage(self) -> dict:
        return {"generations": self.n_generations,
                "total_new_tokens": self.total_tokens,
                "total_seconds": round(self.total_seconds, 1)}
