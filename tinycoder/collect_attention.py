"""Strict collector for Session 009 causal tracing, edits and 70-task scores."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .attention_steering import EDITABLE_LAYERS, SCAN_LAYERS, SOURCE_COMMIT
from .collect_fusion import ALL, START as PRIOR_START, check_saved_factors, check_score

START = "<!-- ATTENTION-STEERING-START -->"
END = "<!-- ATTENTION-STEERING-END -->"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(root):
    trace = read_json(root / "incoming_trace/trace_report.json")
    report = read_json(root / "incoming_steering/report.json")
    predictions = read_json(root / "incoming_steering/predictions.json")
    previous = read_json(root / "experiments/hybrid_fusion_comparison.json")
    progress = read_json(root / "experiments/2026-11-04-rome20/progress.json")
    if (trace.get("status") != "traced_and_frozen" or trace.get("session") != "009"
            or trace.get("source_commit") != SOURCE_COMMIT or report.get("status") != "completed"
            or report.get("session") != "009" or report.get("source_commit") != SOURCE_COMMIT
            or report.get("branch") != "exp/06-attn-steering"
            or trace.get("reference_task_ids") != progress.get("selected_failing_ids")
            or report.get("reference_task_ids") != progress.get("selected_failing_ids")
            or report.get("task_ids") != ALL or predictions.get("task_ids") != ALL
            or not (trace.get("no_training") and report.get("no_training"))):
        raise ValueError("Trace, model, branch, task order or source commit mismatch")
    if set(row["layer"] for row in trace["attention_scan"]) != set(SCAN_LAYERS):
        raise ValueError("Causal output patch tracing did not scan every requested layer 10..18")
    chosen = trace.get("selected_head_edits", [])
    if (len(chosen) != 2 or len(set(row["layer"] for row in chosen)) != 2
            or any(row["layer"] not in EDITABLE_LAYERS for row in chosen)
            or {row["category"] for row in chosen} != {"loop_state", "variable_tracking"}):
        raise ValueError("Must select two distinct allowed attention matrices and logic proxies")
    if trace.get("selected_layers") != [row["layer"] for row in chosen]:
        # The category assignment preserves the ranked ordering of the layers.
        raise ValueError("Chosen layer ordering differs from the causal layer ranking")
    if (not 0.09998 <= trace["archived_layer8_mlp_relative_norm"] <= 0.10002
            or trace["attention_norm_cap"] != .015):
        raise ValueError("Frozen MLP factor or attention constraint does not match declared plan")
    for row in chosen:
        edit = row["edit"]
        if (edit["rank"] != 1 or not 0 < edit["observed_relative_frobenius_change"] <= .015001
                or not 0 <= row["head"] < trace["head_count"]):
            raise ValueError("Attention edit rank/norm/head is invalid")
    expected = [f"layer{row['layer']}.self_attn_o_proj.{side}"
                for row in chosen for side in ("left", "right")]
    expected.extend(("layer8.mlp_down_proj.left", "layer8.mlp_down_proj.right"))
    check_saved_factors(root / "incoming_trace/attn_steering_factors.safetensors", expected)

    score = report["scores"]
    check_score(score, ALL)
    old_baseline = previous["comparisons"]["memit_10"]["passed_ids_before"]
    if score["passed_ids_before"] != old_baseline:
        raise ValueError("Archived 70-task baseline differs from Session 008")
    records = predictions["cases"]
    if ([row["task_id"] for row in records] != ALL
            or sum(bool(row["after_passed"]) for row in records) != score["after_passes"]
            or sum(bool(row["before_passed"]) for row in records) != score["before_passes"]):
        raise ValueError("Task-level source predictions do not match aggregate pass@1")
    return trace, report, previous


def result_markdown(trace, report, previous):
    score = report["scores"]
    comparison = previous["comparisons"]
    rows = [("1.5% Layer 8 MLP MEMIT", comparison["memit_1p5"]),
            ("10% Layer 8 MLP MEMIT", comparison["memit_10"]),
            ("SVD + 10% Layer 8 fusion", comparison["svd_norm_fusion"]),
            ("**Layer 8 MLP + two causal attention head edits**", score)]
    lines = [START,
             "### Session 009: attention-focused causal tracing and logic steering",
             "",
             "Nine attention output matrices (`self_attn.o_proj`) were intervention-tested across layers **10–18** "
             "on the original 20 failure/reference examples. Two matrices were selected from the requested "
             "**12–16** range, with one source-AST-based loop-state proxy and one variable-reassignment proxy. "
             "These labels are heuristic, not independently validated logic circuits.",
             "",
             "| Selection | Head | Proxy task type | Patch Δlog p(reference token) | Observed relative weight edit |",
             "| --- | ---: | --- | ---: | ---: |"]
    for item in trace["selected_head_edits"]:
        lines.append(f"| Layer {item['layer']} `self_attn.o_proj` | {item['head']} | "
                     f"{item['category'].replace('_', ' ')} | {item['head_delta_logprob']:+.6f} | "
                     f"{100*item['edit']['observed_relative_frobenius_change']:.3f}% |")
    lines.extend(["",
                  "The two head-column-restricted rank-one updates were combined with the unchanged archived "
                  "**10% layer 8 `mlp.down_proj`** factor. No backpropagation, optimizer steps or gradient training.",
                  "",
                  "| 70-task comparison (HumanEval/94–163) | Baseline pass@1 | Edited pass@1 "
                  "| Syntax-valid after | New passes | Regressions |",
                  "| --- | ---: | ---: | ---: | --- | --- |"])
    for name, row in rows:
        lines.append(f"| {name} | {row['before_passes']}/70 ({row['pass_at_1_before']:.1%}) | "
                     f"{row['after_passes']}/70 ({row['pass_at_1_after']:.1%}) | "
                     f"{row['syntax_after']['valid']}/70 ({row['syntax_after']['valid']/70:.1%}) | "
                     f"{', '.join(row['newly_passed_ids']) or 'None'} | "
                     f"{', '.join(row['regressed_ids']) or 'None'} |")
    lines.extend(["",
                  f"**Causal mediation proxy:** {trace['causal_metric']}. "
                  "This metric is not proof of variable-tracking competence or logical correctness. "
                  "AST-valid output is distinct from passing all assertions in restricted Docker containers.",
                  "",
                  "**Evaluation caveat:** all 70 tasks were used by previous model comparisons; "
                  "these scores are exploratory and cannot serve as a fresh independent validation.",
                  "",
                  "Artifacts: [`attn_steering_trace.json`](experiments/attn_steering_trace.json), "
                  "[`attn_steering_report.json`](experiments/attn_steering_report.json), "
                  "[`attn_steering_predictions.json`](experiments/attn_steering_predictions.json), "
                  "[`attn_steering_comparison.json`](experiments/attn_steering_comparison.json), "
                  "and [reversible `attn_steering_factors.safetensors`](experiments/attn_steering_factors.safetensors).",
                  END])
    return "\n".join(lines)


def publish(root):
    trace, report, previous = verify(root)
    readme = root / "README.md"
    old = readme.read_text(encoding="utf-8")
    if old.count(START) != 1 or old.count(END) != 1:
        raise RuntimeError("Missing or duplicated Session009 bounded README markers")
    updated = old[:old.index(START)] + result_markdown(trace, report, previous) + old[old.index(END)+len(END):]
    path = root / "experiments"
    for src, dst in (("incoming_trace/trace_report.json", "attn_steering_trace.json"),
                     ("incoming_trace/attn_steering_factors.safetensors", "attn_steering_factors.safetensors"),
                     ("incoming_steering/report.json", "attn_steering_report.json"),
                     ("incoming_steering/predictions.json", "attn_steering_predictions.json")):
        shutil.copyfile(root / src, path / dst)
    comparison = {"status": "completed", "source_commit": SOURCE_COMMIT,
                  "baseline_note": "Historic baseline: 50 prior Session007 plus 20 Session008 completions",
                  "scores": report["scores"], "trace": "experiments/attn_steering_trace.json",
                  "previous_scores": previous["comparisons"], "no_training": True,
                  "caution": "70 tasks were reused; post-selection exploratory results only"}
    (path / "attn_steering_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    readme.write_text(updated, encoding="utf-8")
    print("Published verified attention-layer/head tracing, factor archive and execution comparison", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    publish(Path(parser.parse_args().root))
