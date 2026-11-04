"""Publish Session 013 only after both independently completed CPU/Docker tracks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .session013 import (ANCHOR_BLOB_SHA, BENCHMARK_SEED, FAILURE_BINS, MODEL_ID,
                        TASK_COUNT, summarize)


def collect(baseline_dir: Path, anchor_dir: Path, output_dir: Path, readme: Path):
    from .rome20 import save_json

    tracks = {}
    for name, directory in (("baseline", baseline_dir), ("anchor", anchor_dir)):
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        predictions = json.loads((directory / "predictions.json").read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (report["status"] != "completed" or report["track"] != name
                or report["model"] != MODEL_ID or report["training_steps"] != 0
                or report["factor_git_blob_sha"] != ANCHOR_BLOB_SHA
                or report["dataset_manifest"] != manifest):
            raise ValueError(f"Invalid {name} provenance")
        if not (len(predictions) == len(report["task_results"]) == TASK_COUNT):
            raise ValueError(f"Incomplete {name} evaluation")
        ids = manifest["task_ids"]
        if (len(ids) != TASK_COUNT or len(set(ids)) != TASK_COUNT
                or manifest["selection_seed"] != BENCHMARK_SEED
                or manifest["human_eval_normalized_prompt_overlap"]
                or manifest["prior_experimental_overlap"]):
            raise ValueError("Task selection is not frozen and disjoint")
        if ([r["task_id"] for r in report["task_results"]] != ids
                or [r["task_id"] for r in predictions] != ids):
            raise ValueError(f"Task ordering mismatch for {name}")
        if summarize(report["task_results"]) != report["metrics"]:
            raise ValueError(f"Metrics cannot be reconstructed from {name} cases")
        tracks[name] = (report, predictions, manifest)

    base, base_preds, manifest = tracks["baseline"]
    edited, edit_preds, edit_manifest = tracks["anchor"]
    if manifest != edit_manifest:
        raise ValueError("Independent benchmark datasets differ between tracks")
    if (base["parameter_count"] != edited["parameter_count"]
            or base["factor_sha256"] != edited["factor_sha256"]
            or base["observed_relative_frobenius"] != 0.0
            or abs(edited["observed_relative_frobenius"] - 0.10) > 0.000015):
        raise ValueError("Parameter/anchor invariants violated")
    if (base["max_new_tokens"], base["batch_size"], base["temperature"]) != (
            edited["max_new_tokens"], edited["batch_size"], edited["temperature"]):
        raise ValueError("The two generations have different decoding settings")

    before = {r["task_id"]: r for r in base["task_results"]}
    after = {r["task_id"]: r for r in edited["task_results"]}

    def paired_measure(key):
        gained = [task_id for task_id in manifest["task_ids"]
                  if not before[task_id][key] and after[task_id][key]]
        regressed = [task_id for task_id in manifest["task_ids"]
                     if before[task_id][key] and not after[task_id][key]]
        return {"before_count": sum(x[key] for x in before.values()),
                "after_count": sum(x[key] for x in after.values()),
                "percentage_point_delta": len(gained) - len(regressed),
                "newly_passed_ids": gained, "regressed_ids": regressed}

    comparison = {
        "mbpp_base_execution": paired_measure("base_pass"),
        "mbpp_plus_execution": paired_measure("plus_pass"),
        "syntax_validity": paired_measure("syntax_valid"),
    }
    transition_cases = [
        {"task_id": task_id, "baseline": before[task_id], "anchor": after[task_id],
         "baseline_completion": base_preds[i]["completion"],
         "anchor_completion": edit_preds[i]["completion"]}
        for i, task_id in enumerate(manifest["task_ids"])
    ]
    if any(row["task_id"] != base_preds[i]["task_id"] for i, row in enumerate(transition_cases)):
        raise AssertionError("Per-task prediction pairing failed")

    report = {
        "status": "completed", "session": "013", "branch": "exp/11-mbpp-generalization",
        "model": MODEL_ID, "parameter_count": base["parameter_count"],
        "parameter_scale_unchanged": True, "training_steps": 0,
        "dataset": "100 fixed MBPP test-split problems with EvalPlus MBPP+ base/expanded inputs",
        "dataset_manifest": manifest,
        "independence": "Previously unused by our experiment pipeline, distinct task IDs and normalized prompts from all HumanEval; pretrained contamination cannot be excluded",
        "anchor_commit": base["factor_source_commit"],
        "factor_git_blob_sha": ANCHOR_BLOB_SHA,
        "factor_sha256": base["factor_sha256"],
        "observed_edit_frobenius": edited["observed_relative_frobenius"],
        "decoding": {"max_new_tokens": base["max_new_tokens"],
                     "batch_size": base["batch_size"], "temperature": 0},
        "evaluation": "EvalPlus 0.3.1 per-problem checker in network-disabled Docker; base MBPP and expanded MBPP+ cases, pass@1 from one greedy sample",
        "comparison": comparison,
        "baseline": base["metrics"], "anchor": edited["metrics"],
        "failure_taxonomy_shift": {
            key: {"baseline": base["metrics"]["failure_taxonomy"][key]["count"],
                  "anchor": edited["metrics"]["failure_taxonomy"][key]["count"]}
            for key in (*FAILURE_BINS, "syntax_invalid")},
        "per_task_predictions": "experiments/session013_generalization_predictions.json",
        "limitations": "100 problems, single decoding seed; MBPP+ is an augmentation of MBPP, not a second independent 100-task dataset. Failure labels are conservative diagnostic proxies. No guarantee against inclusion in Qwen pretraining.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(output_dir / "session013_generalization_report.json", report)
    save_json(output_dir / "session013_generalization_predictions.json", transition_cases)

    def fmt(key, attr):
        b, a = base["metrics"][key], edited["metrics"][key]
        return f"{b}/{TASK_COUNT} ({b}%)", f"{a}/{TASK_COUNT} ({a}%)"

    rows = []
    for label, key in (("MBPP base pass@1", "base_pass_count"),
                       ("MBPP+ strict pass@1", "plus_pass_count"),
                       ("Syntax validity", "syntax_valid_count")):
        old, new = fmt(key, None)
        rows.append(f"| {label} | {old} | {new} | {edited['metrics'][key] - base['metrics'][key]:+d} pp |")
    fragment = """## Session 013 — independent MBPP/MBPP+ generalization (measured)

Exactly 100 fixed MBPP test-split problems, selected before generation, were
scored once per model with **Qwen2.5-Coder-0.5B**. The edited model changes
only Layer8 `mlp.down_proj` by the exact archived 10% factor from `e100c62`.
The MBPP base and EvalPlus expanded suites reuse the same **100 prompts**;
they must **not** be counted as 200 independent problems. All generated code
ran only inside CPU-only, read-only, unprivileged, network-disabled Docker.

| Measure | Untouched baseline | 10% Layer8 anchor | Difference |
| --- | ---: | ---: | ---: |
""" + "\n".join(rows) + "\n\n" + """The frozen task IDs, passed/failed lists, per-task predictions, failure
taxonomy changes, and reproducibility hashes are in
[`session013_generalization_report.json`](experiments/session013_generalization_report.json)
and [`session013_generalization_predictions.json`](experiments/session013_generalization_predictions.json).
This is independent of the **prior experiment task set**, not a guarantee
of non-exposure during the model's original pretraining. The 100-task
comparison remains statistically uncertain.

"""
    previous = readme.read_text(encoding="utf-8")
    if "## Session 013 —" in previous:
        raise ValueError("README already contains Session 013; refusing duplicate publication")
    if not previous.startswith("# "):
        raise ValueError("Unrecognized README header")
    first_line, remainder = previous.split("\n", 1)
    readme.write_text(first_line + "\n\n" + fragment + remainder.lstrip("\n"), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--anchor-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("experiments"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    report = collect(args.baseline_dir, args.anchor_dir, args.output_dir, args.readme)
    print(json.dumps(report["comparison"], indent=2))


if __name__ == "__main__":
    main()
