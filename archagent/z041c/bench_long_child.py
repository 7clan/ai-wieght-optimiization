"""Session 041C — child process for ONE longer-code-generation benchmark run.

Invoked only by archagent.z041c.bench_long (the parent). Loads a model in
fp32 with threads=2 (the harness path), greedily decodes up to a token
budget on a trusted teacher-authored prompt, measures load/generation/RSS,
computes structural quality signals on the RAW model output and writes one
JSON evidence file. The raw text is stored verbatim (attribution:
QWEN_GENERATED; never edited by the agent).
"""
from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from pathlib import Path


def distinct_3(text: str) -> float:
    """Share of distinct word-level 3-grams among all 3-grams (1.0 = no
    repetition; low = degeneration). Returns 1.0 for texts under 3 words."""
    words = text.lower().split()
    if len(words) < 3:
        return 1.0
    grams = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
    return len(set(grams)) / len(grams)


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: bench_long_child MODEL_DIR PROMPT_FILE BUDGET OUT_JSON SEED", file=sys.stderr)
        return 2
    model_dir, prompt_file, budget, out_json, seed = (
        Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4]), int(sys.argv[5]))

    import torch
    torch.set_num_threads(2)
    from transformers import AutoModelForCausalLM, AutoTokenizer

    prompt = prompt_file.read_text(encoding="utf-8")

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(model_dir)
    t_tok = time.time() - t0
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32).eval()
    t_load = time.time() - t0
    rss_load = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    n_params = sum(p.numel() for p in model.parameters())
    torch.manual_seed(seed)

    inputs = tok(prompt, return_tensors="pt", add_special_tokens=False)
    with torch.inference_mode():
        t0 = time.time()
        out = model.generate(**inputs, max_new_tokens=budget, do_sample=False,
                             pad_token_id=tok.eos_token_id)
        t_gen = time.time() - t0
    n_new = int(out.shape[1] - inputs["input_ids"].shape[1])
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    text = tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    # new-line count via token ids so whitespace-only continuations are counted
    eos_hit = n_new < budget

    record = {
        "model_dir": str(model_dir),
        "params": n_params,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "budget": budget,
        "seed": seed,
        "decoding": "greedy",
        "threads": 2,
        "tokenizer_load_s": round(t_tok, 3),
        "model_load_s": round(t_load, 3),
        "rss_after_load_mb": round(rss_load, 1),
        "gen_tokens": n_new,
        "natural_eos": bool(eos_hit),
        "gen_s": round(t_gen, 3),
        "tokens_per_s": round(n_new / t_gen, 3) if t_gen > 0 else None,
        "peak_rss_mb": round(rss_peak, 1),
        "chars": len(text),
        "lines": text.count("\n"),
        "brace_balance": text.count("{") - text.count("}"),
        "paren_balance": text.count("(") - text.count(")"),
        "distinct_3": round(distinct_3(text), 4),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "attribution": "QWEN_GENERATED_RAW_UNEDITED",
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "text": text,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "text"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
