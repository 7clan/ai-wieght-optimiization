"""Verify published Session010 artifacts, correcting a diagnosed taxonomy false positive."""

from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path
import shutil

from .session010 import BINS, LAYERS, RANK, classify_failure, valid_failed_cases
from .fusion_validation import contiguous_tasks
from .collect_fusion import ALL, check_score


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_categories(raw: dict, predictions: dict, problems: list[dict]) -> dict:
    """Reclassify FROM archived Docker evidence; never rerun untrusted code here."""
    target = copy.deepcopy(raw)
    lookup = {p["task_id"]: p for p in problems}
    records = {x["task_id"]: x for x in predictions["cases"]}
    failures, valid = valid_failed_cases(problems, predictions)
    if (target["syntax_valid_count"] != len(valid)
            or target["failed_syntax_valid_count"] != len(failures)
            or [x["task_id"] for x in target["cases"]] != [x[0]["task_id"] for x in failures]):
        raise ValueError("Docker diagnostics do not match exact completed predictions")
    for row in target["cases"]:
        selected = classify_failure(lookup[row["task_id"]], records[row["task_id"]]["after_completion"],
                                    row["diagnostic"])
        row.update(selected)
    target["bins"] = {name: {"task_ids": [x["task_id"] for x in target["cases"] if x["category"] == name]}
                      for name in BINS}
    for val in target["bins"].values():
        val["count"] = len(val["task_ids"])
    target["unclassified_ids"] = [x["task_id"] for x in target["cases"] if x["category"] is None]
    target["unclassified_count"] = len(target["unclassified_ids"])
    if sum(x["count"] for x in target["bins"].values()) + target["unclassified_count"] != len(failures):
        raise RuntimeError("Taxonomy has duplicate or omitted failures")
    target["classification_revision"] = "Session010 fix: AST-inspect actual candidate() inputs only; expected result (None, ...) does not imply edge-case input"
    return target


def verify_safetensors(path: Path):
    with path.open("rb") as fp:
        header_len = int.from_bytes(fp.read(8), "little")
        if header_len <= 0 or header_len > 1_000_000:
            raise ValueError("Malformed factors safetensors header")
        header = json.loads(fp.read(header_len))
    for layer in LAYERS:
        for side, shape in (("left", [896, RANK]), ("right", [RANK, 896])):
            key = f"layer{layer}.self_attn_o_proj.{side}"
            if header.get(key, {}).get("shape") != shape:
                raise ValueError(f"Bad or missing saved factor {key}")
    for side in ("left", "right"):
        if f"layer8.mlp_down_proj.{side}" not in header:
            raise ValueError("Missing archived Layer8 MLP factors")


def render_readme(report, taxonomy):
    scores = report["scores"]
    session9 = report["session009_hybrid_comparison"]
    lines = ["", "## Session 010: restricted execution-error taxonomy and rank-eight attention surgery", "",
             "The original **19** AST-valid Session009 completions contain **3 passing** and **16 failing** solutions. "
             "The 16 failed completions were re-executed in restricted Docker with bounded traceback capture. "
             "These four labels are conservative heuristics; unmatched algorithmic errors remain unclassified.", "",
             "| Failure taxonomy (previous Session009 AST-valid failures) | Count | Task IDs |",
             "| --- | ---: | --- |"]
    for key in BINS:
        row = taxonomy["bins"][key]
        lines.append(f"| {key.replace('_', ' ')} | {row['count']} | {', '.join(row['task_ids']) or '—'} |")
    lines.append(f"| **Unclassified semantic / other** | **{taxonomy['unclassified_count']}** | "
                 f"{', '.join(taxonomy['unclassified_ids']) or '—'} |")
    lines += ["", "Layer 12, 13 and 15 `self_attn.o_proj` each received a capped **rank-eight** direct "
              "SVD-truncated ridge edit (≤1.5% Frobenius), plus the unmodified archived **10% Layer8 MLP** edit. "
              "No gradients or optimizer steps were used. Directions were weighted using source-AST boundary "
              "and return-type **proxies**, not proven causal off-by-one/type circuits.", "",
              "| Model | Execution pass@1 | Syntax-valid completions |",
              "| --- | ---: | ---: |",
              f"| Original baseline | {scores['before_passes']}/70 ({scores['pass_at_1_before']:.2%}) | {scores['syntax_before']['valid']}/70 |",
              f"| Session009 attention hybrid | {session9['prior_passes']}/70 ({session9['prior_passes']/70:.2%}) | {session9['prior_syntax_valid']}/70 |",
              f"| **Session010 rank-eight hybrid** | **{scores['after_passes']}/70 ({scores['pass_at_1_after']:.2%})** | **{scores['syntax_after']['valid']}/70** |",
              "", "A syntactically valid completion can still fail the official assertions. "
              "**All 70 tasks were already used in earlier experiments**, so this is not an independent holdout. "
              "Timeout is not proof of context-window expiry.", "",
              "Artifacts: [`assertion_failure_taxonomy.json`](experiments/assertion_failure_taxonomy.json), "
              "[`highrank_logic_report.json`](experiments/highrank_logic_report.json), "
              "[`highrank_logic_predictions.json`](experiments/highrank_logic_predictions.json), "
              "[`highrank_taxonomy_shift.json`](experiments/highrank_taxonomy_shift.json), "
              "[`highrank_factor_report.json`](experiments/highrank_factor_report.json), and "
              "[reversible factors](experiments/highrank_logic_factors.safetensors).", ""]
    return "\n".join(lines)


def publish(args):
    root = Path(args.root)
    import gzip
    problems = [json.loads(line) for line in gzip.open(args.dataset_gzip, "rt", encoding="utf-8")]
    if len(problems) != 164:
        raise ValueError("Official dataset has changed")
    original = read(root / "incoming_taxonomy/assertion_failure_taxonomy.json")
    old_pred = read(root / "prior/experiments/attn_steering_predictions.json")
    taxonomy = refresh_categories(original, old_pred, problems)
    if (taxonomy["syntax_valid_count"] != 19 or taxonomy["failed_syntax_valid_count"] != 16
            or taxonomy["syntax_valid_passed_count"] != 3):
        raise ValueError("Session009 previous diagnostic accounting mismatch")
    report = read(root / "incoming_highrank/highrank_logic_report.json")
    predictions = read(root / "incoming_highrank/highrank_logic_predictions.json")
    factor_report = read(root / "incoming_highrank/highrank_factor_report.json")
    raw_shift = read(root / "incoming_highrank/highrank_taxonomy_shift.json")
    if (report.get("status") != "completed" or report.get("session") != "010"
            or report.get("branch") != "exp/07-highrank-logic-boost"
            or report.get("task_ids") != ALL or predictions.get("task_ids") != ALL
            or factor_report.get("rank_per_matrix") != 8 or factor_report.get("layers") != list(LAYERS)
            or not report.get("no_training")):
        raise ValueError("Surgery report/branch/benchmark provenance mismatch")
    check_score(report["scores"], ALL)
    if (report["scores"]["before_passes"] != 2
            or report["session009_hybrid_comparison"]["prior_passes"] != 3):
        raise ValueError("Unrecognized historical comparison baseline")
    for layer in LAYERS:
        if not 0 < factor_report["factor_metadata"][str(layer)]["observed_relative_norm"] <= .015001:
            raise ValueError("Measured rank-eight matrix norm exceeded cap")
    verify_safetensors(root / "incoming_highrank/highrank_logic_factors.safetensors")
    if (raw_shift["prior_syntax_valid_failures"] != 16
            or raw_shift["after_syntax_valid_failures"] !=
            sum(not x["after_passed"] for x in predictions["cases"] if x["task_id"] in report["scores"]["syntax_after"]["valid_ids"])):
        raise ValueError("Report taxonomy differs from generated execution records")
    corrected_after = refresh_categories({
        "cases": raw_shift["after_details"],
        "syntax_valid_count": report["scores"]["syntax_after"]["valid"],
        "failed_syntax_valid_count": raw_shift["after_syntax_valid_failures"]}, predictions, problems)
    shift = {"prior_syntax_valid_failures": 16,
             "after_syntax_valid_failures": corrected_after["failed_syntax_valid_count"],
             "before_bins": taxonomy["bins"], "after_bins": corrected_after["bins"],
             "before_unclassified": taxonomy["unclassified_count"],
             "after_unclassified": corrected_after["unclassified_count"],
             "after_details": corrected_after["cases"],
             "classification_revision": taxonomy["classification_revision"]}
    report["taxonomy_shift"] = shift
    out = root / "experiments"
    for source, destination in (("highrank_logic_factors.safetensors", "highrank_logic_factors.safetensors"),
                                ("highrank_logic_predictions.json", "highrank_logic_predictions.json"),
                                ("highrank_factor_report.json", "highrank_factor_report.json")):
        shutil.copyfile(root / "incoming_highrank" / source, out / destination)
    for name, value in (("assertion_failure_taxonomy.json", taxonomy),
                        ("highrank_logic_report.json", report),
                        ("highrank_taxonomy_shift.json", shift)):
        (out / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    readme = root / "README.md"
    body = readme.read_text(encoding="utf-8")
    if "## Session 010:" in body:
        raise FileExistsError("Session010 README report already present")
    readme.write_text(body.rstrip() + "\n" + render_readme(report, taxonomy), encoding="utf-8")
    print("SESSION010 VERIFIED", report["scores"]["before_passes"], "->",
          report["scores"]["after_passes"], "syntax", report["scores"]["syntax_after"]["valid"],
          "taxonomy", {k:v["count"] for k,v in taxonomy["bins"].items()}, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--dataset-gzip", required=True)
    publish(p.parse_args())
