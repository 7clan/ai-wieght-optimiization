"""Session 041B — CPU performance benchmark: original vs merged checkpoint.

Measures, per model directory, in isolated one-shot subprocess trials
(3 trials each, fresh process = cold module state):
  * tokenizer load time (s);
  * model load time (s, from_pretrained fp32 — the harness load path);
  * peak RSS after load (MB);
  * greedy generation: prompt-processing + steady-state decode of 128
    new tokens on a FIXED neutral prompt (not from any suite), with
    threads=2 (the harness setting) — tokens/s overall and peak RSS;
  * total wall time.

Runs both the frozen base and the merged checkpoint under an identical
protocol and writes a JSON comparison + markdown table.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/z041-coding-finetune/bench/cpu-bench.json"

TRIALS = 3
N_TOKENS = 128
# Neutral fixed prompt (not from any suite/curriculum/holdout).
PROMPT = (
    "// utility helpers for a small booking tool\n"
    "export function nights(checkIn, checkOut) {\n"
    "  const msPerDay = 24 * 60 * 60 * 1000;\n"
    "  return Math.round((Date.parse(checkOut) - Date.parse(checkIn)) / msPerDay);\n"
    "}\n\n"
    "export function totalPrice(nights, ratePerNight) {\n"
)

ONE_SHOT = r"""
import json, resource, sys, time
sys.path.insert(0, ".")
import torch
torch.set_num_threads(2)
from transformers import AutoModelForCausalLM, AutoTokenizer
model_dir = sys.argv[1]
t0 = time.time()
tok = AutoTokenizer.from_pretrained(model_dir)
t_tok = time.time() - t0
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32).eval()
t_load = time.time() - t0
rss_load = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
n_params = sum(p.numel() for p in model.parameters())
torch.manual_seed(20261111)
inputs = tok(%r, return_tensors="pt", add_special_tokens=False)
with torch.inference_mode():
    t0 = time.time()
    out = model.generate(**inputs, max_new_tokens=%d, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    t_gen = time.time() - t0
n_new = int(out.shape[1] - inputs["input_ids"].shape[1])
rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
print(json.dumps({
    "tokenizer_load_s": round(t_tok, 3),
    "model_load_s": round(t_load, 3),
    "rss_after_load_mb": round(rss_load, 1),
    "gen_tokens": n_new,
    "gen_s": round(t_gen, 3),
    "tokens_per_s": round(n_new / t_gen, 3),
    "peak_rss_mb": round(rss_peak, 1),
    "params": n_params,
}))
""" % (PROMPT, N_TOKENS)


def run_trial(model_dir: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", ONE_SHOT, model_dir],
        cwd=str(ROOT), text=True, capture_output=True, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"trial failed: {proc.stderr[-800:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--merged-dir", required=True)
    args = parser.parse_args()

    results = {}
    for label, d in (("original", args.base_dir), ("merged", args.merged_dir)):
        trials = []
        for i in range(TRIALS):
            t = run_trial(d)
            trials.append(t)
            print(label, i + 1, json.dumps(t), flush=True)
        results[label] = trials

    def agg(label):
        ts = results[label]
        return {
            "model_load_s": [round(t["model_load_s"], 3) for t in ts],
            "model_load_s_mean": round(statistics.mean(t["model_load_s"] for t in ts), 3),
            "tokens_per_s": [t["tokens_per_s"] for t in ts],
            "tokens_per_s_mean": round(statistics.mean(t["tokens_per_s"] for t in ts), 3),
            "peak_rss_mb": [t["peak_rss_mb"] for t in ts],
            "peak_rss_mb_max": round(max(t["peak_rss_mb"] for t in ts), 1),
            "params": ts[0]["params"],
        }

    out = {
        "protocol": {
            "trials": TRIALS, "new_tokens": N_TOKENS, "threads": 2,
            "dtype": "fp32 load (harness path)", "decoding": "greedy",
            "prompt": PROMPT,
            "machine": "2 vCPU sandbox, 3.9 GiB RAM, no GPU",
        },
        "original": agg("original"),
        "merged": agg("merged"),
        "raw_trials": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("protocol", "original", "merged")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
