"""Publish measured final validation and 70-task hybrid results, never guesses."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path

from .fusion_validation import SOURCE_COMMIT

START = "<!-- FUSION-VALIDATION-START -->"
END = "<!-- FUSION-VALIDATION-END -->"
OLD = [f"HumanEval/{i}" for i in range(94, 144)]
NEW = [f"HumanEval/{i}" for i in range(144, 164)]
ALL = OLD + NEW


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_score(score, expected_ids):
    count = len(expected_ids)
    if (score["n"] != count or len(score["passed_ids_before"]) != score["before_passes"]
            or len(score["passed_ids_after"]) != score["after_passes"]
            or len(score["failed_ids_after"]) != count - score["after_passes"]
            or set(score["passed_ids_after"]) | set(score["failed_ids_after"]) != set(expected_ids)
            or set(score["passed_ids_after"]) & set(score["failed_ids_after"])):
        raise ValueError("Incomplete benchmark scores or invalid task partitions")
    for field in ("syntax_before", "syntax_after"):
        if score[field]["valid"] + score[field]["invalid"] != count:
            raise ValueError("Invalid AST syntax counts")


def check_saved_factors(path, expected_keys):
    """Read safetensors' JSON header without importing tensors or running code."""
    if path.stat().st_size < 100:
        raise ValueError("Reversible factors are missing or empty")
    with path.open("rb") as stream:
        header_len = struct.unpack("<Q", stream.read(8))[0]
        if not 1 <= header_len < 200_000:
            raise ValueError("Invalid safetensors header size")
        header = json.loads(stream.read(header_len))
    if set(header) - {"__metadata__"} != set(expected_keys):
        raise ValueError("Incorrect fused tensor factor keys")
    for key in expected_keys:
        entry = header[key]
        if (not all(v > 0 for v in entry["shape"])
                or entry["dtype"] not in ("F32", "F16", "BF16")):
            raise ValueError("Invalid fused factor shape or dtype")


def combine_scores(fifty, twenty):
    check_score(fifty, OLD)
    check_score(twenty, NEW)
    before = fifty["passed_ids_before"] + twenty["passed_ids_before"]
    after = fifty["passed_ids_after"] + twenty["passed_ids_after"]
    return {"n": 70, "before_passes": len(before), "after_passes": len(after),
            "pass_at_1_before": len(before) / 70, "pass_at_1_after": len(after) / 70,
            "percentage_point_delta": (len(after) - len(before)) * 100 / 70,
            "passed_ids_before": before, "passed_ids_after": after,
            "failed_ids_before": [x for x in ALL if x not in before],
            "failed_ids_after": [x for x in ALL if x not in after],
            "newly_passed_ids": [x for x in after if x not in before],
            "regressed_ids": [x for x in before if x not in after],
            "syntax_before": {"valid": fifty["syntax_before"]["valid"] + twenty["syntax_before"]["valid"]},
            "syntax_after": {"valid": fifty["syntax_after"]["valid"] + twenty["syntax_after"]["valid"]}}


def prepare(root: Path):
    old10 = read_json(root / "experiments/exp03_norm_break_report.json")
    old15 = read_json(root / "experiments/exp04_memit_single_report.json")
    validation = read_json(root / "incoming_validation/report.json")
    fusion = read_json(root / "incoming_fusion/report.json")
    if (validation.get("status") != "completed" or validation.get("track") != "final_holdout_validation"
            or validation.get("source_commit") != SOURCE_COMMIT or validation.get("task_ids") != NEW
            or fusion.get("status") != "completed" or fusion.get("track") != "svd_norm_fusion"
            or fusion.get("source_commit") != SOURCE_COMMIT or fusion.get("task_ids") != ALL
            or fusion.get("branch") != "exp/05-svd-norm-fusion"
            or old10.get("variant") != "norm_break" or old15.get("variant") != "memit_single"
            or old10.get("holdout_ids") != OLD or old15.get("holdout_ids") != OLD
            or not all(x.get("no_training") for x in (old10, old15, validation, fusion))):
        raise ValueError("Experiment provenance/holdout chronology mismatch")
    fif10 = old10["variants"]["10%"]
    fif15 = old15["variants"]["default"]
    if fif10["passed_ids_before"] != fif15["passed_ids_before"]:
        raise ValueError("Historical baselines disagree")
    val10, val15 = validation["scores"]["memit_10"], validation["scores"]["memit_1p5"]
    if val10["passed_ids_before"] != val15["passed_ids_before"]:
        raise ValueError("New 20-task baselines disagree")
    merged10 = combine_scores(fif10, val10)
    merged15 = combine_scores(fif15, val15)
    score_fusion = fusion["scores"]
    check_score(score_fusion, ALL)
    if score_fusion["passed_ids_before"] != merged10["passed_ids_before"]:
        raise ValueError("Hybrid baseline is not identical to both existing comparators")
    if (not 0.09998 < fusion["factors"]["mlp_relative_change"] < 0.10002
            or not 0.1179 < fusion["factors"]["attention_relative_change"] < 0.1181):
        raise ValueError("Saved factor applications were not the requested edits")
    factor_path = root / "incoming_fusion/hybrid_fusion_factors.safetensors"
    check_saved_factors(factor_path, ("layer8.self_attn_o_proj.left", "layer8.self_attn_o_proj.right",
                                      "layer8.mlp_down_proj.left", "layer8.mlp_down_proj.right"))
    result = {"status": "completed", "source_commit": SOURCE_COMMIT,
              "validation_holdout": "HumanEval/144–163, 20 tasks, originally reserved after Session 007",
              "comparator_scope": "HumanEval/94–163, 70 tasks; older 50 previously model-compared",
              "comparisons": {"memit_1p5": merged15, "memit_10": merged10, "svd_norm_fusion": score_fusion},
              "validation20": validation["scores"],
              "no_training": True,
              "limitations": "The hybrid's 70-task results include the previously consumed model-comparison set and the 20-task final confirmation set. This is not a new independent hybrid holdout."}
    return result, validation, fusion


def table_row(name, score):
    return (f"| {name} | {score['before_passes']}/{score['n']} ({score['pass_at_1_before']:.1%}) "
            f"| {score['after_passes']}/{score['n']} ({score['pass_at_1_after']:.1%}) "
            f"| **{score['percentage_point_delta']:+.2f} pp** "
            f"| {score['syntax_before']['valid']}/{score['n']} "
            f"| {score['syntax_after']['valid']}/{score['n']} "
            f"| {', '.join(score['newly_passed_ids']) or 'None'} "
            f"| {', '.join(score['regressed_ids']) or 'None'} |")


def markdown(result):
    rows = result["comparisons"]
    validation = result["validation20"]
    return "\n".join([
        START,
        "### Session 008: out-of-sample confirmation and Layer 8 hybrid fusion",
        "",
        "**Final unused holdout:** the preselected 10% Layer 8 edit was evaluated first on "
        "HumanEval/144–163 (20 tasks), before constructing or scoring the hybrid.",
        "",
        "| Fresh 20-task validation | Baseline pass@1 | Edited pass@1 | Change | AST valid before | AST valid after | New passes | Regressions |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        table_row("Preselected 10% Layer 8 MEMIT", validation["memit_10"]),
        table_row("Archived 1.5% Layer 8 MEMIT comparator", validation["memit_1p5"]),
        "",
        "**70-task comparison (HumanEval/94–163):** previously recorded results on 94–143 "
        "were combined with the 20-task validation results for each MEMIT candidate. "
        "The new SVD-hybrid was executed on all 70 tasks. All rows use identical task IDs.",
        "",
        "| Intervention | Baseline pass@1 | Edited pass@1 | Change | AST valid before | AST valid after | New passes | Regressions |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        table_row("1.5% Layer 8 MEMIT", rows["memit_1p5"]),
        table_row("10% Layer 8 MEMIT", rows["memit_10"]),
        table_row("[SVD + 10% hybrid](https://github.com/7clan/ai-wieght-optimiization/tree/exp/05-svd-norm-fusion)", rows["svd_norm_fusion"]),
        "",
        "The hybrid removes the two previously identified singular components from layer 8 "
        "`self_attn.o_proj`, then applies the archived 10% multi-key Layer 8 `mlp.down_proj` edit. "
        "No layer 12 change, gradients, optimizer steps, or training.",
        "",
        "**Interpretation:** AST syntax validity only means `ast.parse(prompt + completion)` succeeded; "
        "it is not execution correctness. pass@1 means all official HumanEval assertions passed inside "
        "restricted Docker containers. The 70-task hybrid comparison is **not** an independent validation "
        "of the hybrid because these tasks have already been used for prior comparisons.",
        "",
        "Evidence: [`final_holdout_validation.json`](experiments/final_holdout_validation.json), "
        "[`hybrid_fusion_report.json`](experiments/hybrid_fusion_report.json), "
        "[`hybrid_fusion_comparison.json`](experiments/hybrid_fusion_comparison.json), "
        "[`hybrid_fusion_predictions.json`](experiments/hybrid_fusion_predictions.json), and "
        "[reversible `hybrid_fusion_factors.safetensors`](experiments/hybrid_fusion_factors.safetensors).",
        END,
    ])


def publish(root: Path):
    result, validation, fusion = prepare(root)
    readme = root / "README.md"
    before = readme.read_text(encoding="utf-8")
    if before.count(START) != 1 or before.count(END) != 1:
        raise ValueError("Expected exactly one precreated README fusion result placeholder")
    updated = before[:before.index(START)] + markdown(result) + before[before.index(END) + len(END):]
    target = root / "experiments"
    for source, name in (
        ("incoming_validation/report.json", "final_holdout_validation.json"),
        ("incoming_validation/predictions.json", "final_holdout_validation_predictions.json"),
        ("incoming_fusion/report.json", "hybrid_fusion_report.json"),
        ("incoming_fusion/predictions.json", "hybrid_fusion_predictions.json"),
        ("incoming_fusion/hybrid_fusion_factors.safetensors", "hybrid_fusion_factors.safetensors"),
    ):
        shutil.copyfile(root / source, target / name)
    (target / "hybrid_fusion_comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    readme.write_text(updated, encoding="utf-8")
    print("Published 20-task final validation and 70-task fusion comparison", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    publish(Path(parser.parse_args().root))
