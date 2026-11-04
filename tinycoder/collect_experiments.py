"""Verify four immutable job artifacts, archive each, and render comparison.

This never runs model-generated code, never invents a score, and refuses to
publish an incomplete or overlapping evaluation.  Called by the collector job.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

EXPECTED = {
    "transplant": ("01-transplant", "exp01_transplant"),
    "svd_zeroing": ("02-svd-zeroing", "exp02_svd_zeroing"),
    "norm_break": ("03-norm-break", "exp03_norm_break"),
    "memit_single": ("04-memit-single-layer", "exp04_memit_single"),
}
START = "<!-- HIGH-RISK-EXPERIMENTS-START -->"
END = "<!-- HIGH-RISK-EXPERIMENTS-END -->"


def prepare_comparison(artifacts: Path):
    expected_tasks = [f"HumanEval/{idx}" for idx in range(94, 144)]
    reports = {}
    baseline_ids = None
    for variant, (artifact_id, _name) in EXPECTED.items():
        folder = artifacts / f"branch-{artifact_id}-results"
        if not all((folder / f).is_file() for f in ("report.json", "predictions.json", "factors.safetensors")):
            raise FileNotFoundError(f"Missing measured report/factors/predictions for {variant}: {folder}")
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        if (report.get("status") != "completed" or report.get("variant") != variant
                or report.get("holdout_ids") != expected_tasks or not report.get("no_training")):
            raise ValueError(f"Invalid or overlapping task report for {variant}")
        if variant == "norm_break" and set(report.get("variants", {})) != {"3%", "5%", "10%"}:
            raise ValueError("Stress experiment must contain all three thresholds")
        if variant != "norm_break" and set(report.get("variants", {})) != {"default"}:
            raise ValueError(f"Unexpected scoring variants for {variant}")
        for name, score in report["variants"].items():
            if score["n"] != 50 or len(score["passed_ids_before"]) != score["before_passes"]:
                raise ValueError(f"Invalid before-score for {variant}/{name}")
            if len(score["passed_ids_after"]) != score["after_passes"]:
                raise ValueError(f"Invalid after-score for {variant}/{name}")
            if any(idx not in expected_tasks for idx in score["passed_ids_after"]):
                raise ValueError(f"Task leakage in {variant}/{name}")
            if baseline_ids is None:
                baseline_ids = score["passed_ids_before"]
            if score["passed_ids_before"] != baseline_ids:
                raise ValueError("Baseline differs across parallel jobs; direct comparison would be unreliable")
        if variant in ("transplant", "memit_single") and report["intervention"]["observed_relative_delta_norm"] > 0.015001:
            raise ValueError(f"1.5% cap exceeded in {variant}")
        reports[variant] = report

    return reports


def comparison_markdown(reports):
    out = [START,
           "### Session 007: four independent high-risk CPU branches",
           "",
           "Every branch used the untouched **HumanEval/94–143** comparison set (50 tasks) "
           "and the original base Qwen2.5-Coder-0.5B checkpoint. "
           "The same holdout is now **used for model comparison**; future choices need "
           "a different final validation set.",
           "",
           "| Isolated branch and method | Baseline pass@1 | Edited pass@1 | Change | New passes | Regressions |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for variant, (artifact_id, basename) in EXPECTED.items():
        report = reports[variant]
        for label, score in report["variants"].items():
            suffix = "" if label == "default" else f" ({label})"
            out.append(
                f"| [`{artifact_id}`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/{artifact_id}){suffix} "
                f"| {score['before_passes']}/50 ({score['pass_at_1_before']:.0%}) "
                f"| {score['after_passes']}/50 ({score['pass_at_1_after']:.0%}) "
                f"| **{score['percentage_point_delta']:+.1f} pp** "
                f"| {len(score['newly_passed_ids'])} | {len(score['regressed_ids'])} |"
            )
    out.extend(["",
                "Each branch's exact passed/failed task IDs, activation measurements, "
                "tensor changes, and predictions are archived in `experiments/exp0*_report.json`, "
                "`experiments/exp0*_predictions.json`, and reversible `experiments/exp0*_factors.safetensors`.",
                "",
                "**Caution:** SVD projection gaps are only *associated* with syntax-invalid examples. "
                "Cross-layer transplantation is not established as a way to transfer skills. "
                "The 3%, 5%, and 10% stress trials can locate only the first *tested* failure threshold, "
                "not an exact continuous breakdown point. Results do not prove general coding improvements.",
                END])
    return "\n".join(out)


def publish(artifacts: Path, experiments: Path, readme: Path):
    reports = prepare_comparison(artifacts)
    output = {"status": "completed", "untouched_at_start": "HumanEval/94..143",
              "method": "four independent CPU direct-weight interventions; 4 PyTorch threads",
              "reports": {name: f"experiments/{basename}_report.json"
                          for name, (_artifact, basename) in EXPECTED.items()},
              "comparisons": {variant: report["variants"] for variant, report in reports.items()},
              "no_training": True,
              "caution": "Comparative holdout is now seen; new evaluation needed before choosing a winner"}

    body = readme.read_text(encoding="utf-8")
    if body.count(START) != 1 or body.count(END) != 1:
        raise RuntimeError("README missing unique high-risk experiment result markers")
    updated = body[:body.index(START)] + comparison_markdown(reports) + body[body.index(END)+len(END):]
    experiments.mkdir(parents=True, exist_ok=True)
    for variant, (artifact_id, basename) in EXPECTED.items():
        src = artifacts / f"branch-{artifact_id}-results"
        for from_name, to_name in (("report.json", f"{basename}_report.json"),
                                   ("predictions.json", f"{basename}_predictions.json"),
                                   ("factors.safetensors", f"{basename}_factors.safetensors")):
            shutil.copyfile(src / from_name, experiments / to_name)
    (experiments / "high_risk_comparison.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    readme.write_text(updated, encoding="utf-8")
    print("Verified all four reports and saved cross-branch results", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Publish measured results of four isolated experiment jobs")
    parser.add_argument("--artifacts", default="branch_artifacts")
    parser.add_argument("--experiments", default="experiments")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()
    publish(Path(args.artifacts), Path(args.experiments), Path(args.readme))


if __name__ == "__main__":
    main()
