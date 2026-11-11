"""Session 041B — paired before/after coding correctness on the frozen v2 dev split.

Implements the frozen evaluation plan (SESSION040 TRAINING_PROPOSAL.md §5)
primary endpoints, paired base-vs-merged, under the s040 protocol EXACTLY:

  * dev split, radiostation domain (6 tasks: one per skill family);
  * Track A (unassisted single-shot) and Track B (contract-first) — the
    same frozen prompts (prompts.build_track_a/b), the same greedy
    decoding, the same deterministic seeds (seed_for — hash-derived, so
    identical to Session 040's), the same L-TRIM extraction + forced-
    continuation retry (experiments.run_pair, imported unmodified);
  * evaluation inside the restricted execution tier (archagent.s040.exec,
    unshare backend on this box, verdicts fail-closed);
  * per-candidate vocabulary-lock violations: occurrences of the
    greenhouse demo nouns (the 040 taxonomy word list) in the final
    candidate — the dominant 040 failure mode (11/17);
  * EXECUTION_FAILED rate from the verdict statuses.

Evidence: one JSON per (track, task) + a summary table per model label,
written under experiments/z041-coding-finetune/eval/<label>/. Resumable.
The 24 holdout tasks remain sealed (never loaded; the s039 loader refuses
them and this driver never passes final_score_unlocked).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.s040 import experiments as s040exp  # noqa: E402
from archagent.s040 import prompts  # noqa: E402

EVAL_ROOT = ROOT / "experiments/z041-coding-finetune/eval"
DEV_DOMAIN = "radiostation"

# Session-040 failure-taxonomy word list (greenhouse demo vocabulary).
DEMO_NOUN_RE = re.compile(
    r"\b(greenhouses?|sensors?|calibrating|monitoring|readings?)\b", re.IGNORECASE)


def vocab_lock_violations(candidate: str) -> int:
    return len(DEMO_NOUN_RE.findall(candidate or ""))


def evidence_path(label: str, track: str, entry: dict) -> Path:
    return EVAL_ROOT / label / f"track-{track}" / f"{entry['domain']}__{entry['skill']}.json"


def load_dev_sample(repo: Path) -> list[dict]:
    sample = [e for e in s040exp.load_sample(repo)
              if e["domain"] == DEV_DOMAIN]
    assert len(sample) == 6, len(sample)
    return sample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True,
                        help="checkpoint directory (frozen base or merged)")
    parser.add_argument("--label", required=True,
                        help="evidence label, e.g. base / merged")
    parser.add_argument("--tracks", nargs="*", default=["A", "B"])
    args = parser.parse_args()

    repo = ROOT.resolve()
    sample = load_dev_sample(repo)
    print(json.dumps({"label": args.label, "model_dir": args.model_dir,
                      "dev_tasks": len(sample),
                      "skills": sorted(e["skill"] for e in sample)}))

    model = None
    for track in args.tracks:
        for entry in sample:
            out_path = evidence_path(args.label, track, entry)
            if out_path.is_file():
                print(f"skip existing {out_path.name}")
                continue
            if model is None:
                from archagent.model import FrozenModel
                model = FrozenModel(args.model_dir, threads=2)
            t0 = time.time()
            try:
                record = s040exp.run_pair(repo, model, track, entry,
                                          backend="auto", image=None)
            except Exception as error:  # fail-closed, never crash the batch
                record = {"track": track, "task_id": entry["id"],
                          "skill": entry["skill"], "domain": entry["domain"],
                          "error": str(error)[:300],
                          "verdict": {"passed": False, "status": "DRIVER_ERROR"}}
            record["model_label"] = args.label
            record["model_dir"] = args.model_dir
            record["vocab_lock_violations"] = vocab_lock_violations(
                record.get("candidate_final", ""))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            v = record.get("verdict", {})
            print(f"{track} {entry['id']}: {'PASS' if v.get('passed') else 'FAIL'} "
                  f"({v.get('status')}) vocablock={record['vocab_lock_violations']} "
                  f"[{time.time() - t0:.0f}s]", flush=True)

    # ---- summary -------------------------------------------------------------
    rows = []
    for track in args.tracks:
        for entry in sample:
            p = evidence_path(args.label, track, entry)
            if p.is_file():
                rows.append(json.loads(p.read_text(encoding="utf-8")))
    summary = {"label": args.label, "model_dir": args.model_dir,
               "protocol": "s040 frozen v2 dev split (radiostation), greedy, "
                           "seed_for(track,task) — identical to Session 040",
               "pairs": len(rows)}
    for track in args.tracks:
        tr = [r for r in rows if r["track"] == track]
        summary[f"track_{track}"] = {
            "n": len(tr),
            "passed": sum(1 for r in tr if r.get("verdict", {}).get("passed") is True),
            "statuses": {s: sum(1 for r in tr if r.get("verdict", {}).get("status") == s)
                         for s in sorted({r.get("verdict", {}).get("status", "?")
                                          for r in tr})},
            "vocab_lock_violations_total": sum(r.get("vocab_lock_violations", 0) for r in tr),
            "candidates_with_violations": sum(1 for r in tr
                                              if r.get("vocab_lock_violations", 0) > 0),
            "gen_tokens": sum(a.get("usage", {}).get("tokens", 0)
                              for r in tr for a in r.get("attempts", [])),
            "gen_seconds": round(sum(a.get("usage", {}).get("seconds", 0)
                                     for r in tr for a in r.get("attempts", [])), 1),
            "wall_seconds": round(sum(r.get("wall_seconds", 0) for r in tr), 1),
        }
    out = EVAL_ROOT / args.label / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
