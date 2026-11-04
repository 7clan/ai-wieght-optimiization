"""Combine measured CPU Action artifacts into a verified Session012 release.

Requires both Action jobs to finish successfully. Never fabricate a score
or use benchmark data to derive a new surgery direction.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session012 import ALPHAS, COUNT, OPERATORS, START, archived_anchor


def make_row(name, data):
    score = data["execution"]
    diag = data["diagnostics"]
    if data["status"] != "completed" or score is None or diag["status"] != "finite":
        raise ValueError(f"Experiment variant {name} not successfully benchmarked")
    valid = score["syntax_after"]["valid"]
    after_passes = score["after_passes"]
    taxonomy = data["taxonomy"]
    if taxonomy["n_syntax_valid_failed"] != valid - after_passes:
        raise ValueError(f"Assertion-taxonomy accounting mismatch: {name}")
    return {"variant": name, "pass_count": after_passes,
            "pass_at_1": score["pass_at_1_after"],
            "passed_ids": score["passed_ids_after"], "failed_ids": score["failed_ids_after"],
            "ast_valid_count": valid, "ast_validity": score["syntax_validity_after"],
            "token_perplexity": diag["token_perplexity"],
            "token_entropy_nats": diag["token_entropy_nats"],
            "syntax_valid_assertion_failures": taxonomy["n_syntax_valid_failed"],
            "failure_bins": {k: v["count"] for k, v in taxonomy["bins"].items()},
            "operator_trigger_counts": data.get("hook_stats", {}).get("operator_token_counts", {}),
            "changed_completions_vs_base": score["changed_completions"]}


def load_result(directory, track):
    directory = Path(directory)
    report = json.loads((directory / "session012_extreme_report.json").read_text())
    predictions = json.loads((directory / "session012_extreme_predictions.json").read_text())
    if report["track"] != track or report["status"] != "completed":
        raise ValueError(f"{track} run is not complete")
    ids = [f"HumanEval/{i}" for i in range(START, START+COUNT)]
    if report["benchmark_ids"] != ids or predictions["task_ids"] != ids:
        raise ValueError(f"{track}: wrong task list")
    if len(report["source_failure_ids"]) != 50 or any(
            int(i.rsplit("/", 1)[1]) >= START for i in report["source_failure_ids"]):
        raise ValueError(f"{track}: training data leaked benchmark tasks")
    for name, rows in predictions["variants"].items():
        if len(rows) != COUNT or [r["task_id"] for r in rows] != ids:
            raise ValueError(f"Incomplete predictions for {name}")
    return report, predictions, directory


def combine(hooks_dir, surgery_dir, reference_taxonomy, output_dir, readme):
    hooks, hooks_predictions, _ = load_result(hooks_dir, "hooks")
    surgery, surgery_predictions, surgery_path = load_result(surgery_dir, "surgery")
    for attribute in ("base_model", "dataset", "source_failure_ids", "source_archive_sha256", "benchmark_ids"):
        if hooks[attribute] != surgery[attribute]:
            raise ValueError(f"Track provenance mismatch: {attribute}")
    if hooks["anchor"]["file_sha256"] != surgery["anchor"]["file_sha256"]:
        raise ValueError("Archived 10% anchor factor mismatch")
    if set(hooks["variants"]) != {f"hooks_alpha_{a:g}" for a in ALPHAS}:
        raise ValueError("Missing hook alpha sweep")
    if set(surgery["variants"]) != {"rank64_static"} | {
            f"rank64_hooks_alpha_{a:g}" for a in ALPHAS}:
        raise ValueError("Missing rank64/combined alpha variants")
    variants = {**hooks["variants"], **surgery["variants"]}
    rows = {name: make_row(name, entry) for name, entry in variants.items()}
    archive_anchor = archived_anchor(
        "experiments/exp03_norm_break_predictions.json",
        "experiments/final_holdout_validation_predictions.json")
    anchor_passes = [row["task_id"] for row in archive_anchor if row["after_passed"]]
    if anchor_passes != hooks["anchor"]["passed_ids"]:
        raise ValueError("Historical anchor record mismatch")
    previous_report = json.loads(Path("experiments/exp03_norm_break_report.json").read_text())
    final_report = json.loads(Path("experiments/final_holdout_validation.json").read_text())
    anchor_syntax = (previous_report["variants"]["10%"]["syntax_after"]["valid"]
                     + final_report["scores"]["memit_10"]["syntax_after"]["valid"])
    if anchor_syntax != 18 or len(anchor_passes) != 3:
        raise ValueError("Historical 10% anchor scores unexpectedly changed")
    winner_hooks = max((rows[f"hooks_alpha_{a:g}"] for a in ALPHAS),
                       key=lambda row: (row["pass_count"], row["ast_valid_count"]))
    winner_fusion = max((rows[f"rank64_hooks_alpha_{a:g}"] for a in ALPHAS),
                        key=lambda row: (row["pass_count"], row["ast_valid_count"]))
    static = rows["rank64_static"]
    reference = json.loads(Path(reference_taxonomy).read_text())
    if (reference["status"] != "completed" or
            reference["benchmark_ids"] != hooks["benchmark_ids"] or
            reference["baseline"]["n_syntax_valid_failed"] != 5 or
            reference["anchor_10pct"]["n_syntax_valid_failed"] != 15):
        raise ValueError("Reference taxonomy must cover the same 70 tasks")
    anchor_bins = {name: entry["count"] for name, entry in
                   reference["anchor_10pct"]["bins"].items()}
    anchor = {"variant": "archived_10pct_layer8", "pass_count": 3,
              "pass_at_1": 3 / COUNT, "passed_ids": anchor_passes,
              "ast_valid_count": anchor_syntax,
              "token_perplexity": hooks["anchor"]["diagnostics"]["token_perplexity"],
              "token_entropy_nats": hooks["anchor"]["diagnostics"]["token_entropy_nats"]}
    baseline = {"variant": "archived_untouched_0p5b", "pass_count": 2,
                "pass_at_1": 2 / COUNT, "passed_ids": hooks["baseline"]["passed_ids"],
                "ast_valid_count": 7,
                "token_perplexity": hooks["baseline"]["diagnostics"]["token_perplexity"],
                "token_entropy_nats": hooks["baseline"]["diagnostics"]["token_entropy_nats"]}
    if len(baseline["passed_ids"]) != 2:
        raise ValueError("Historical untouched base pass set changed")
    compared = [baseline, anchor, winner_hooks, static, winner_fusion]
    report = {
        "status": "completed", "session": "012", "branch": "exp/10-extreme-overdrive",
        "model": hooks["base_model"], "model_size_unchanged": True,
        "methods": {"anchor": "archived exact 10% Layer8 MLP edit",
                    "hooks": "operator token conditional +alpha*unit reference residual, layers13 and15",
                    "rank64": "100-key ridge via two states per each of 50 pre-94 pairs, thin-QR rank64 SVD",
                    "combined": "anchor + three rank64 matrices + same dynamic hooks"},
        "benchmark_ids": hooks["benchmark_ids"], "reused_benchmark_not_independent": True,
        "source_failure_ids": hooks["source_failure_ids"],
        "operator_vocabulary": list(OPERATORS), "alpha_sweep": list(ALPHAS),
        "comparison": compared,
        "all_variants": rows,
        "best_hooks_alpha": float(winner_hooks["variant"].rsplit("_", 1)[-1]),
        "best_combined_alpha": float(winner_fusion["variant"].rsplit("_", 1)[-1]),
        "alpha_peak_is_discrete_not_global": True,
        "first_sampled_entropy_spike_alpha": {
            "hooks": hooks["dynamic"]["first_sampled_spike_alpha"],
            "combined": surgery["dynamic"]["first_sampled_spike_alpha"]},
        "failure_shift": {name: {"syntax_valid_assertion_failures_vs_anchor":
                          row["syntax_valid_assertion_failures"] - (anchor_syntax - len(anchor_passes)),
                          "assertion_failure_bins": row["failure_bins"],
                          "bin_count_delta_vs_anchor": {bucket: count - anchor_bins[bucket]
                                                        for bucket, count in row["failure_bins"].items()}}
                          for name, row in rows.items()},
        "reference_failure_taxonomy": reference,
        "factor_file": "experiments/session012_extreme_factors.safetensors",
        "per_task_predictions_file": "experiments/session012_extreme_predictions.json",
        "source_artifact_provenance": {"hooks": "session012-extreme-hooks",
                                       "surgery": "session012-extreme-surgery"},
        "statistical_limitations": "Same HumanEval 94..163 as multiple earlier comparisons, selection over nine variants inflates exploratory best; reference residual vectors are proxies; two-position reference states are not token-aligned causal targets; few alpha samples do not determine an exact breakdown threshold.",
        "raw_tracks": {"hooks": hooks, "surgery": surgery}}
    merged_predictions = {"task_ids": hooks["benchmark_ids"],
                          "variants": {**hooks_predictions["variants"],
                                       **surgery_predictions["variants"]}}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(output_dir / "session012_extreme_report.json", report)
    save_json(output_dir / "session012_extreme_predictions.json", merged_predictions)
    source_factors = surgery_path / "session012_extreme_factors.safetensors"
    destination = output_dir / "session012_extreme_factors.safetensors"
    shutil.copyfile(source_factors, destination)
    report["factor_sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
    save_json(output_dir / "session012_extreme_report.json", report)

    def tab_row(label, row):
        return (f"| {label} | {row['pass_count']}/{COUNT} "
                f"({100*row['pass_at_1']:.1f}%) | {row['ast_valid_count']}/{COUNT} "
                f"({100*row['ast_valid_count']/COUNT:.1f}%) | "
                f"{row['token_perplexity']:.3f} | {row['token_entropy_nats']:.3f} |")

    table = ["| Model intervention | Execution pass@1 | AST-valid syntax | Reference token PPL | Token entropy (nats) |",
             "| --- | ---: | ---: | ---: | ---: |"]
    table += [tab_row(label, row) for label, row in (
        ("Untouched 0.5B", baseline), ("Archived Layer8 10%", anchor),
        (f"Hook sweep best α={report['best_hooks_alpha']:g}", winner_hooks),
        ("Three-matrix rank64", static),
        (f"Rank64 + hooks best α={report['best_combined_alpha']:g}", winner_fusion))]
    body = Path(readme).read_text(encoding="utf-8")
    begin = body.index("## Session 012 —")
    end = body.index("A beginner-friendly experiment", begin)
    replacement = ("## Session 012 — Qwen2.5-Coder-0.5B extreme overdrive (measured)\n\n"
                   + "All nine variants ran on four-thread GitHub CPU runners; all generated code "
                   + "was tested inside network-disabled, read-only Docker. "
                   + "HumanEval/94–163 is **reused and exploratory**, not independent.\n\n"
                   + "\n".join(table) + "\n\n"
                   + "The hook vocabulary is `for`, `while`, `if`, `return`, `def`, `range`; "
                   + "the tested α values are 0.5, 1.0, 1.75, 2.5. "
                   + "**The best listed alpha is a discrete tested setting, not a mathematical optimum.** "
                   + "Rank64 requires two tokens per 50 frozen source pairs (100 columns), "
                   + "not impossible rank64 from only 50 last-token vectors. "
                   + "All directions are teacher-activation proxies, not established logic circuits.\n\n"
                   + "Measured error-taxonomy shifts, per-task predictions, observed trigger counts, "
                   + "and reversible factors: "
                   + "[`session012_extreme_report.json`](experiments/session012_extreme_report.json), "
                   + "[`session012_extreme_predictions.json`](experiments/session012_extreme_predictions.json), "
                   + "`experiments/session012_extreme_factors.safetensors`.\n\n")
    Path(readme).write_text(body[:begin] + replacement + body[end:], encoding="utf-8")
    print("SESSION012 FINAL MATRIX")
    print("\n".join(table))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks-dir", required=True)
    parser.add_argument("--surgery-dir", required=True)
    parser.add_argument("--reference-taxonomy", required=True)
    parser.add_argument("--output-dir", default="experiments")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()
    combine(args.hooks_dir, args.surgery_dir, args.reference_taxonomy,
            args.output_dir, args.readme)


if __name__ == "__main__":
    main()
