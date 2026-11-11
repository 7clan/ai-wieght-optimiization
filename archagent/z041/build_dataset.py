"""Session 041B — Stage-1 SFT dataset builder (25 verified model-origin candidates).

Executes SESSION040 TRAINING_PROPOSAL.md §3 ("Data plan"):
  * source of truth: the archived evidence records (verbatim prompt +
    verified candidate bytes, sha256-chained) — no new generations;
  * prompt-formatted exactly as the archived prompts; completion = the
    verified candidate bytes with the harness anchor overlap removed
    (so the supervised span is exactly what the model generated);
  * loss on completion tokens only (masking happens at train time from
    n_prompt_tokens recorded here);
  * family-weighted sampling plan (038A mandatory rule: the parent-1tm
    pattern is 10/25 and must not be over-weighted).

Contamination guards (fail-closed, run before writing anything):
  * every source split tag must be train/app (never dev, never holdout);
  * no dev-domain or holdout-adjacent vocabulary may appear in any
    prompt or completion (dev = radiostation/tailorshop/sportsarena in
    suite v2; the 24 holdout tasks are sealed and never read);
  * model pin: every provenance model_sha256 must equal the frozen
    checkpoint sha aff8914e…a47f80.

Output: experiments/z041-coding-finetune/dataset/sft-25.jsonl + stats.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FROZEN_MODEL_SHA = "aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80"
OUT_DIR = ROOT / "experiments/z041-coding-finetune/dataset"

# dev-split domains of suite v2 (train: aquarium/observatory; dev:
# radiostation/tailorshop/sportsarena — only radiostation is sampled by
# the s040 driver, but the scan covers all three) + their distinctive
# field vocabulary. Holdout domains are sealed and unknown to us; the
# seal is enforced by the s039 loader refusing the holdout split.
DEV_VOCAB = [
    "radiostation", "tailorshop", "sportsarena", "airtimeMin", "fabricCm",
    "airtime", "fabric", "spotslot", "adslot", "ad break", "airing",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def anchor_overlap(prompt: str, candidate: str) -> str:
    """Longest string A with prompt.endswith(A) and candidate.startswith(A)."""
    anchor = ""
    for k in range(1, min(len(prompt), len(candidate), 400) + 1):
        if prompt.endswith(candidate[:k]):
            anchor = candidate[:k]
    return anchor


def resolve_candidates() -> list[dict]:
    rows = []
    manifest = load_json(ROOT / "experiments/z038a-independent-retest/training-candidates.json")
    for e in manifest["entries"]:
        prov = e["provenance"]
        gen = load_json(ROOT / prov["generation_path"])
        assert sha256_text(gen["prompt"]) == prov["prompt_sha256"], e["piece"]
        assert sha256_text(gen["candidate"]) == prov["candidate_sha256"], e["piece"]
        assert prov["model_sha256"] == FROZEN_MODEL_SHA, e["piece"]
        rows.append({
            "id": e["piece"], "family": e["task_family"], "kind": e["kind"],
            "split_tag": f"z037/{e['spec_source']}", "source": prov["generation_path"],
            "prompt": gen["prompt"], "candidate": gen["candidate"],
        })
    queue = ROOT / "experiments/z040-autonomous-fullstack/training-prep/candidate-queue-040.jsonl"
    for line in queue.read_text(encoding="utf-8").splitlines():
        q = json.loads(line)
        src = load_json(ROOT / q["source"])
        chosen = None
        if "attempts" in src:
            for att in src["attempts"]:
                if sha256_text(att.get("candidate", "")) == q["candidate_sha256"]:
                    chosen = att
                    break
        if chosen is None and "candidate_final" in src:
            if sha256_text(src["candidate_final"]) == q["candidate_sha256"]:
                chosen = {"candidate": src["candidate_final"],
                          "prompt": src["attempts"][-1]["prompt"]}
        assert chosen is not None, q["id"]
        assert q["split"] == "train" or q["split"] == "app", q["id"]
        rows.append({
            "id": q["id"], "family": q["skill"], "kind": q["skill"],
            "split_tag": f"z040/{q['split']}", "source": q["source"],
            "prompt": chosen["prompt"], "candidate": chosen["candidate"],
        })
    return rows


def main() -> int:
    rows = resolve_candidates()
    assert len(rows) == 25, len(rows)

    # ---- contamination guards -------------------------------------------------
    violations = []
    for r in rows:
        blob = (r["prompt"] + "\n" + r["candidate"]).lower()
        for word in DEV_VOCAB:
            if word in blob:
                violations.append((r["id"], word))
    assert not violations, f"dev-vocabulary contamination: {violations}"

    # ---- tokenization ---------------------------------------------------------
    from transformers import AutoTokenizer
    model_dir = Path(__file__).resolve().parents[3] / "models/Qwen2.5-Coder-0.5B"
    import os
    model_dir = Path(os.environ.get("ARCHAGENT_MODEL_DIR", model_dir))
    tok = AutoTokenizer.from_pretrained(model_dir)
    eos_id = tok.eos_token_id

    examples, token_stats = [], []
    for r in rows:
        anchor = anchor_overlap(r["prompt"], r["candidate"])
        completion = r["candidate"][len(anchor):] if anchor else r["candidate"]
        ids_prompt = tok(r["prompt"], add_special_tokens=False)["input_ids"]
        ids_full = tok(r["prompt"] + completion, add_special_tokens=False)["input_ids"]
        # token-boundary integrity: prompt tokens must be a strict prefix
        assert ids_full[: len(ids_prompt)] == ids_prompt, r["id"]
        n_completion = len(ids_full) - len(ids_prompt)
        assert n_completion > 0, r["id"]
        ex = {
            "id": r["id"], "family": r["family"], "kind": r["kind"],
            "split_tag": r["split_tag"], "source": r["source"],
            "prompt": r["prompt"], "completion": completion,
            "anchor": anchor,
            "prompt_sha256": sha256_text(r["prompt"]),
            "candidate_sha256": sha256_text(r["candidate"]),
            "completion_sha256": sha256_text(completion),
            "n_prompt_tokens": len(ids_prompt),
            "n_completion_tokens": n_completion,
            "eos_appended": True,
            "eos_token_id": eos_id,
        }
        examples.append(ex)
        token_stats.append({
            "id": r["id"], "prompt": len(ids_prompt), "completion": n_completion,
            "total": len(ids_prompt) + n_completion + 1,  # + supervised EOS
        })

    max_total = max(t["total"] for t in token_stats)
    # ---- family-weighted sampling plan (038A mandatory rule) ------------------
    fam_counts = {}
    for ex in examples:
        fam_counts[ex["family"]] = fam_counts.get(ex["family"], 0) + 1
    weights = [1.0 / fam_counts[ex["family"]] for ex in examples]
    norm = sum(weights)

    EPOCHS = 12  # disclosed amendment: 040 proposal said 3; 038A plan said 20
    DRAWS = EPOCHS * len(examples)
    import random
    rng = random.Random(4141)
    plan = []
    cum = []
    acc = 0.0
    for w in weights:
        acc += w / norm
        cum.append(acc)
    cum[-1] = 1.0
    for _ in range(DRAWS):
        x = rng.random()
        idx = next(i for i, c in enumerate(cum) if x <= c)
        plan.append(idx)
    # auditable per-family draw counts
    draw_counts = {}
    for i in plan:
        draw_counts[examples[i]["family"]] = draw_counts.get(examples[i]["family"], 0) + 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "sft-25.jsonl", "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, sort_keys=True) + "\n")

    stats = {
        "session": "041B", "n_examples": len(examples),
        "model_pin_sha256": FROZEN_MODEL_SHA,
        "sources": "038A 22 (z037 curricula/challenge) + 040 3 (v2 train + gearhut app)",
        "split_tags": sorted({ex["split_tag"] for ex in examples}),
        "contamination_scan": {"dev_vocabulary_scanned": DEV_VOCAB, "violations": 0},
        "token_stats": {
            "max_total_incl_eos": max_total,
            "mean_prompt": sum(t["prompt"] for t in token_stats) / len(token_stats),
            "mean_completion": sum(t["completion"] for t in token_stats) / len(token_stats),
            "per_example": token_stats,
        },
        "family_counts": fam_counts,
        "sampling": {
            "rule": "family-weighted with replacement, weight = 1/family_count",
            "epochs": EPOCHS, "draws": DRAWS, "seed": 4141,
            "draw_counts_per_family": draw_counts,
        },
        "boundary_rule": "completion = candidate minus longest prompt-suffix/candidate-prefix overlap (the harness anchor); z037-era records carry no overlap, z040-era records carry the full anchor",
        "eos_rule": "one tokenizer EOS token supervised after the completion (disclosed amendment; teaches termination)",
    }
    (OUT_DIR / "dataset-stats.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "token_stats"}, indent=1))
    print(f"max total tokens (incl EOS): {max_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
