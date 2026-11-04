"""Replay untouched/archived-10%-anchor failures in Docker for comparable bins."""

import argparse
from pathlib import Path

from .fusion_validation import archived_baseline, contiguous_tasks
from .rome20 import fetch_problems, save_json
from .sandbox_eval import require_sandbox
from .session012 import START, COUNT, archived_anchor, conservative_taxonomy


def run(destination, previous, final):
    problems = contiguous_tasks(fetch_problems(), START, COUNT)
    baseline = archived_baseline(previous, final)
    anchor = archived_anchor(previous, final)
    if len(baseline) != COUNT or len(anchor) != COUNT:
        raise ValueError("Archived benchmark incomplete")
    base_records = [{"task_id": row["task_id"], "after_passed": row["passed"],
                     "after_completion": row["completion"]} for row in baseline]
    anchor_records = [{"task_id": row["task_id"], "after_passed": row["after_passed"],
                       "after_completion": row["after_completion"]} for row in anchor]
    base_taxonomy = conservative_taxonomy(problems, base_records)
    anchor_taxonomy = conservative_taxonomy(problems, anchor_records)
    result = {"status": "completed", "session": "012", "benchmark_ids":
              [x["task_id"] for x in problems], "benchmark_reused": True,
              "baseline": base_taxonomy, "anchor_10pct": anchor_taxonomy}
    if base_taxonomy["n_syntax_valid_failed"] != 7 - 2:
        raise ValueError("Baseline taxonomy accounting mismatch")
    if anchor_taxonomy["n_syntax_valid_failed"] != 18 - 3:
        raise ValueError("Anchor taxonomy accounting mismatch")
    save_json(destination, result)
    print("BASELINE VS ANCHOR TAXONOMY", base_taxonomy["bins"], anchor_taxonomy["bins"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/session012_taxonomy/session012_reference_taxonomy.json")
    parser.add_argument("--previous", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--final", default="experiments/final_holdout_validation_predictions.json")
    args = parser.parse_args()
    require_sandbox()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(destination, Path(args.previous), Path(args.final))


if __name__ == "__main__":
    main()
