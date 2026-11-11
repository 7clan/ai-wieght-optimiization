"""Session 041B — trunk dtype probe (infrastructure choice, pre-training).

Measures one fwd+bwd micro-step (seq ~979, LoRA r16 on the 6 target
modules, chunked CE) in bf16 vs fp32 on this 2-vCPU box, plus peak RSS,
so the training dtype choice is measured, not guessed. Follows the 038A
Plan-1 intent (bf16 trunk + fp32 LoRA) unless the measurement says
otherwise. Not a hyperparameter sweep: a single probe per dtype.
"""
from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.z041.train_lora import chunked_ce  # noqa: E402

DATASET = ROOT / "experiments/z041-coding-finetune/dataset/sft-25.jsonl"
SEQ_CAP = 979


def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def probe(dtype_name: str) -> dict:
    torch.manual_seed(0)
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model_dir = Path(os.environ["ARCHAGENT_MODEL_DIR"])
    tok = AutoTokenizer.from_pretrained(model_dir)
    dtype = torch.bfloat16 if dtype_name == "bf16" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=dtype)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "up_proj", "down_proj"]))
    base = model.get_base_model()
    base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    trunk, lm_head = base.model, base.lm_head
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                            lr=2e-4)

    ex = json.loads(DATASET.read_text(encoding="utf-8").splitlines()[23])  # the longest (979 tok)
    ids_c = tok(ex["prompt"] + ex["completion"], add_special_tokens=False)["input_ids"]
    ids = ids_c + [ex["eos_token_id"]]
    n_prompt = len(tok(ex["prompt"], add_special_tokens=False)["input_ids"])
    assert len(ids) <= SEQ_CAP + 1, len(ids)
    input_ids = torch.tensor([ids], dtype=torch.long)
    labels = input_ids.clone()
    labels[0, :n_prompt] = -100
    n_sup = int((labels != -100).sum())

    times = []
    for i in range(3):
        torch.manual_seed(i)
        t0 = time.time()
        h = trunk(input_ids=input_ids).last_hidden_state
        loss = chunked_ce(h, labels, lm_head, n_sup)
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        times.append(time.time() - t0)
    out = {
        "dtype": dtype_name, "seq_len": len(ids), "loss": float(loss.detach()),
        "step_times_s": [round(t, 2) for t in times],
        "steady_step_s": round(times[-1], 2),
        "peak_rss_mb": round(peak_mb(), 1),
        "loss_finite": bool(torch.isfinite(loss).item()),
    }
    del model, opt
    return out


if __name__ == "__main__":
    results = {}
    for d in ("bf16", "fp32"):
        results[d] = probe(d)
        print(json.dumps(results[d]), flush=True)
    out_path = ROOT / "experiments/z041-coding-finetune/train/dtype-probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    pick = "bf16" if (results["bf16"]["steady_step_s"] <= results["fp32"]["steady_step_s"]
                      and results["bf16"]["peak_rss_mb"] < results["fp32"]["peak_rss_mb"]) else "fp32"
    print("PICK:", pick)
