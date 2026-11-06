"""Evaluation runner for ArchBench: generation, scoring, log-probs, reports.

All conditions (baseline and edited) run through this same path with identical
prompts and greedy decoding, so scores are directly comparable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import torch

from .benchmark import build_prompt, tasks_for
from .scoring import extract_answer, score_answer

MODEL_PATH = "/home/z/models/qwen25-coder-0.5b"
BASE_MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B"
MAX_NEW_TOKENS = 24


def load_model(edit_dirs: list[str] | None = None, device: str = "cpu"):
    """Load the untouched base checkpoint, then apply reversible factor dirs."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from .edits import load_factor_set

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, dtype=torch.float32)
    model.eval()
    applied = []
    if edit_dirs:
        for d in edit_dirs:
            applied.append(load_factor_set(model, d))
    return model, tokenizer, applied


def _tokenize(tokenizer, text: str):
    return tokenizer(text, return_tensors="pt", add_special_tokens=False)


@torch.inference_mode()
def answer_logprobs(model, tokenizer, prompt: str, answer: str) -> dict:
    """Teacher-forced log-probs of an answer continuation (ID concatenation,
    matching how generation appends tokens after the prompt)."""
    prefix_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    answer_ids = tokenizer(answer, add_special_tokens=False)["input_ids"]
    prefix_len = len(prefix_ids)
    full_len = prefix_len + len(answer_ids)
    if not answer_ids:
        return {"mean_logprob": None, "first_token_logprob": None, "n_tokens": 0}
    input_ids = torch.tensor([prefix_ids + answer_ids], dtype=torch.long)
    out = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids))
    logprobs = torch.log_softmax(out.logits[0, prefix_len - 1:full_len - 1].float(), dim=-1)
    targets = input_ids[0, prefix_len:full_len]
    token_lp = logprobs[torch.arange(full_len - prefix_len), targets]
    return {
        "mean_logprob": float(token_lp.mean().item()),
        "first_token_logprob": float(token_lp[0].item()),
        "n_tokens": int(full_len - prefix_len),
    }


@torch.inference_mode()
def generate_answer(model, tokenizer, prompt: str, max_new_tokens: int = MAX_NEW_TOKENS):
    ids = _tokenize(tokenizer, prompt)
    t0 = time.time()
    out = model.generate(
        **ids, max_new_tokens=max_new_tokens, do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
    )
    dt = time.time() - t0
    text = tokenizer.decode(out[0, ids.input_ids.shape[1]:], skip_special_tokens=True)
    return text, dt, int(out.shape[1] - ids.input_ids.shape[1])


def failure_category(task: dict, extracted: str, result: dict) -> str:
    if not extracted.strip():
        return "empty"
    if result["method"] == "mismatch":
        kind = result.get("normalized_gold", "")
        if kind and kind not in result.get("normalized_prediction", ""):
            if task["category"] in ("CON", "XCOM"):
                return "wrong_identifier"
            if task["subcategory"] == "signature":
                return "wrong_signature"
            return "wrong_value"
    return "other"


def syntax_validity(task: dict, extracted: str) -> bool:
    """Structural validity proxy for code-line answers (no execution)."""
    if task["category"] not in ("CON",):
        return True
    text = extracted.strip()
    if not text:
        return False
    if task["subcategory"] == "signature":
        if text.startswith("def "):
            try:
                import ast
                ast.parse(text + "\n    pass")
                return True
            except SyntaxError:
                return False
        return text.startswith("function ") and text.rstrip().endswith("{")
    if task["subcategory"] == "shape":
        if text.startswith("res.") or text.startswith("return "):
            # balanced braces/brackets + quotes check
            pairs = {"{": "}", "[": "]", "(": ")"}
            stack = []
            in_str = None
            for ch in text:
                if in_str:
                    if ch == in_str:
                        in_str = None
                    continue
                if ch in "\"'":
                    in_str = ch
                elif ch in pairs:
                    stack.append(pairs[ch])
                elif ch in "}])":
                    if not stack or stack.pop() != ch:
                        return False
            return not stack
    return True


def evaluate_tasks(model, tokenizer, tasks: list[dict], tag: str,
                   compute_logprob: bool = True) -> dict:
    records = []
    for i, task in enumerate(tasks):
        prompt = build_prompt(task["category"], task["question"])
        gen, dt, ntok = generate_answer(model, tokenizer, prompt)
        extracted = extract_answer(gen)
        result = score_answer(task, extracted)
        rec = {
            "id": task["id"],
            "category": task["category"],
            "subcategory": task["subcategory"],
            "difficulty": task["difficulty"],
            "partition": task["partition"],
            "correct": result["correct"],
            "method": result["method"],
            "failure_category": None if result["correct"] else failure_category(task, extracted, result),
            "syntax_valid": syntax_validity(task, extracted),
            "prediction_raw": gen[:200],
            "prediction_extracted": extracted[:120],
            "normalized_prediction": result["normalized_prediction"][:120],
            "normalized_gold": result["normalized_gold"][:120],
            "generation_seconds": round(dt, 2),
            "generated_tokens": ntok,
        }
        if compute_logprob:
            lp = answer_logprobs(model, tokenizer, prompt, " " + task["gold"])
            rec["gold_mean_logprob"] = lp["mean_logprob"]
            rec["gold_first_token_logprob"] = lp["first_token_logprob"]
        records.append(rec)
        if (i + 1) % 8 == 0:
            done = sum(r["correct"] for r in records)
            print(f"  [{tag}] {i+1}/{len(tasks)} correct so far {done}", flush=True)
    return summarize(records, tag)


def summarize(records: list[dict], tag: str) -> dict:
    def acc(rs):
        return round(sum(r["correct"] for r in rs) / max(1, len(rs)), 4)

    summary = {
        "tag": tag,
        "n": len(records),
        "accuracy": acc(records),
        "by_category": {},
        "by_partition": {},
        "by_category_partition": {},
        "syntax_valid_rate": round(sum(r["syntax_valid"] for r in records) / max(1, len(records)), 4),
        "failure_categories": {},
        "mean_generation_seconds": round(sum(r["generation_seconds"] for r in records) / max(1, len(records)), 3),
        "total_generated_tokens": sum(r["generated_tokens"] for r in records),
        "records": records,
    }
    for cat in ("VAR", "CON", "JSR", "XCOM"):
        rs = [r for r in records if r["category"] == cat]
        summary["by_category"][cat] = acc(rs)
        for part in ("dev", "val", "holdout"):
            rp = [r for r in rs if r["partition"] == part]
            summary["by_category_partition"][f"{cat}/{part}"] = acc(rp)
    for part in ("dev", "val", "holdout"):
        rs = [r for r in records if r["partition"] == part]
        summary["by_partition"][part] = acc(rs)
    fc = {}
    for r in records:
        if not r["correct"]:
            fc[r["failure_category"]] = fc.get(r["failure_category"], 0) + 1
    summary["failure_categories"] = fc
    lps = [r["gold_mean_logprob"] for r in records if r.get("gold_mean_logprob") is not None]
    if lps:
        summary["mean_gold_logprob"] = round(sum(lps) / len(lps), 4)
    return summary


def save_report(report: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"saved {p}")


def paired_comparison(base_records: list[dict], edit_records: list[dict],
                      label_a: str = "baseline", label_b: str = "edit") -> dict:
    """Task-level paired outcomes with a exact McNemar test."""
    from math import comb

    a = {r["id"]: r["correct"] for r in base_records}
    b = {r["id"]: r["correct"] for r in edit_records}
    common = sorted(set(a) & set(b))
    n01 = sum(1 for t in common if not a[t] and b[t])   # baseline wrong, edit right
    n10 = sum(1 for t in common if a[t] and not b[t])   # baseline right, edit wrong
    n00 = sum(1 for t in common if not a[t] and not b[t])
    n11 = sum(1 for t in common if a[t] and b[t])
    # exact binomial McNemar (two-sided) on discordant pairs
    n_d = n01 + n10
    if n_d == 0:
        p_value = 1.0
    else:
        k = min(n01, n10)
        p_value = min(1.0, 2 * sum(comb(n_d, i) for i in range(0, k + 1)) / 2 ** n_d)
    flips = {
        "gained": [t for t in common if not a[t] and b[t]],
        "lost": [t for t in common if a[t] and not b[t]],
    }
    return {
        "label_a": label_a, "label_b": label_b,
        "n": len(common),
        f"{label_a}_correct": n11 + n10,
        f"{label_b}_correct": n11 + n01,
        "both_wrong": n00, "both_right": n11,
        "gained": flips["gained"], "lost": flips["lost"],
        "mcnemar_p": round(p_value, 5),
    }
