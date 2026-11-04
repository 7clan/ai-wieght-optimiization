"""Publish Session014 numbers only after all eight CPU/Docker tracks complete."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .session014 import (ALPHAS, MODEL_ID, TOTAL_COUNT, TRACKS, measure)


def collect(root: Path, prepared_dir: Path, target: Path, readme: Path):
    from .rome20 import save_json
    manifest = json.loads((prepared_dir/"manifest.json").read_text(encoding="utf-8"))
    diag = json.loads((prepared_dir/"diagnostics.json").read_text(encoding="utf-8"))
    if manifest["total"] != TOTAL_COUNT or diag["manifest_sha256"] != manifest["manifest_sha256"]:
        raise ValueError("Prepared factor/dataset manifest mismatch")
    if any(details["max_abs_cross_cosine"] > 1e-5 for name,details in diag["measured_cosine"].items()
           if name.endswith(".subspace")):
        raise ValueError("Orthogonal UI/backend subspaces were not independent")

    reports, predictions = {},{}
    expected_ids = manifest["mbpp_task_ids"] + manifest["web_task_ids"]
    if len(expected_ids) != TOTAL_COUNT or len(set(expected_ids)) != TOTAL_COUNT:
        raise ValueError("Incomplete benchmark manifest")
    for track in TRACKS:
        folder = root/f"session014-track-{track}"
        report = json.loads((folder/"report.json").read_text(encoding="utf-8"))
        preds = json.loads((folder/"predictions.json").read_text(encoding="utf-8"))
        if (report["status"] != "completed" or report["track"] != track
                or report["model"] != MODEL_ID or report["training_steps"] != 0
                or report["manifest"] != manifest
                or report["factor_sha256"] != diag["factor_sha256"]
                or report["parameter_count"] != 494032768
                or len(report["task_results"]) != TOTAL_COUNT
                or len(preds) != TOTAL_COUNT):
            raise ValueError(f"Invalid or missing {track} actual benchmark results")
        if ([r["task_id"] for r in report["task_results"]] != expected_ids
                or [r["task_id"] for r in preds] != expected_ids):
            raise ValueError("Missing or reordered task IDs across comparison tracks")
        for label,subset in (("mbpp_plus",report["task_results"][:50]),
                             ("custom_web",report["task_results"][50:]),
                             ("ui_react",report["task_results"][50:75]),
                             ("backend_express",report["task_results"][75:]),
                             ("overall",report["task_results"])):
            if measure(subset) != report[label]:
                raise ValueError(f"{track} {label} statistics are not reconstructible")
        if track == "baseline" and (report["alpha"] is not None or report["static_edits"]):
            raise ValueError("Baseline checkpoint was not untouched")
        if track == "static" and (report["alpha"] is not None or set(report["static_edits"]) != {"layer8","layer16"}):
            raise ValueError("Static-only track was modified unexpectedly")
        if track.startswith("dynamic-") and report["static_edits"]:
            raise ValueError("Dynamic-only track includes static edits")
        if track.startswith("hybrid-") and set(report["static_edits"]) != {"layer8","layer16"}:
            raise ValueError("Hybrid track omitted static edits")
        for fraction in report["static_edits"].values():
            if not 0 < fraction <= 0.015001:
                raise ValueError("Static edit norm cap was violated")
        reports[track] = report
        predictions[track] = preds

    baseline = reports["baseline"]
    comparisons = {}
    for name in TRACKS:
        result = reports[name]
        baseline_by_id = {r["task_id"]:r for r in baseline["task_results"]}
        after = {r["task_id"]:r for r in result["task_results"]}
        gained = [task for task in expected_ids if not baseline_by_id[task]["execution_pass"] and after[task]["execution_pass"]]
        regressed = [task for task in expected_ids if baseline_by_id[task]["execution_pass"] and not after[task]["execution_pass"]]
        comparisons[name] = {
            "overall":result["overall"],
            "mbpp_plus":result["mbpp_plus"],"ui_react":result["ui_react"],
            "backend_express":result["backend_express"],
            "custom_web":result["custom_web"],
            "alpha":result["alpha"],"trigger_counts":result["trigger_counts"],
            "static_relative_norms":result["static_edits"],
            "newly_passed_ids":gained,"regressed_ids":regressed,
            "pass_at_1_delta_pp":len(gained)-len(regressed),
            "failure_taxonomy_shift": {key:{"baseline":baseline["overall"]["failure_bins"].get(key,0),
                                           "track":result["overall"]["failure_bins"].get(key,0)}
                                       for key in sorted(set(baseline["overall"]["failure_bins"]) |
                                                         set(result["overall"]["failure_bins"]))},
        }
    report = {
        "status":"completed", "session":"014", "branch":"exp/12-hybrid-ortho-hooks",
        "model":MODEL_ID,"parameter_count":baseline["parameter_count"],
        "parameter_scale_unchanged":True,"training_steps":0,
        "dataset_manifest":manifest,"source_trajectory_count":50,
        "source_reference_docker_validated":True,
        "factor_sha256":diag["factor_sha256"],
        "factor_artifact":"experiments/session014_orthogonal_factors.safetensors",
        "orthogonal_subspace_diagnostics":diag["measured_cosine"],
        "steering":"Mode-gated output steering at self_attn.o_proj layers 12,18 on cached single-token decoding only",
        "edit":"Rank<=32 ridge/SVD factors at Layer8 down_proj (UI), Layer16 down_proj (backend), capped at 1.5% per observed matrix",
        "runtime_alphas":list(ALPHAS),
        "tracks":comparisons,
        "execution":"MBPP+ official EvalPlus expanded tests and 50 custom React/Express assertions inside network-disabled, unprivileged, resource-limited Docker",
        "limitations":[
            "Not 100 fresh MBPP+ tasks: 50 previously unused MBPP+ problems and 50 custom authored web scaffolding tasks.",
            "Custom React/Express tasks are derived from five template families each; generalization to independent real-world projects is not established.",
            "The frozen source references and benchmark tasks do not share exact prompts; unseen pretraining data cannot be verified.",
            "SVD/Gram-Schmidt orthogonality in hidden space does not prove mechanistic independence or zero interference.",
            "Hook offsets modify attention o_proj output, not the entire residual stream; triggers depend on single-token decoded keyword matches.",
            "One deterministic completion per task (empirical pass@1); small 50-task per-domain samples have high uncertainty.",
        ],
    }
    target.mkdir(parents=True,exist_ok=True)
    save_json(target/"session014_hybrid_report.json",report)
    save_json(target/"session014_hybrid_predictions.json",{
        name:predictions[name] for name in TRACKS})

    def cell(track,key):
        val = reports[track][key]
        return f"{val['execution_passes']}/{val['count']} ({val['execution_pass_at_1']:.0%})"

    rows=[]
    for track in TRACKS:
        m = reports[track]["overall"]
        rows.append(f"| {track} | {cell(track,'mbpp_plus')} | {cell(track,'ui_react')} | "
                    f"{cell(track,'backend_express')} | {m['execution_passes']}/100 | "
                    f"{m['syntax_valid']}/100 | {comparisons[track]['pass_at_1_delta_pp']:+d} pp |")
    fragment="""## Session 014 — orthogonal subspaces plus dynamic activation hooks (measured)

Qwen2.5-Coder **0.5B base** was run with no gradient training or architecture changes.
Fifty independently selected MBPP+ prompts (excluding Session013's 100 tasks)
and fifty *custom-authored* React/Express scaffolding tasks were evaluated.
React and Express tasks have their own Docker validation—not Python `ast.parse`.
All 50 editing references passed their Docker tests before any factors were
derived; no test prompt was included in the activation derivation set.

UI and backend activation matrices were SVD-decomposed and Gram-Schmidt/QR
orthogonalized, then turned into bounded rank32 changes at Layers 8 and 16.
The runtime tracks applied mode-targeted attention-`o_proj` forward hooks at
Layers 12 and 18 only when an incrementally generated token matched a
control-flow keyword. The hook changes attention output, not whole residual.

| Track | MBPP+ pass@1 (50) | React pass@1 (25) | Express pass@1 (25) | Combined pass@1 | Syntax valid | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""+"\n".join(rows)+"\n\n"+"""The combined total weights 50 Python tasks and 50 custom JavaScript tasks
equally; it is descriptive and **not** a standardized benchmark score.
Exact task-level predictions, failure taxonomy shifts, per-layer cross-subspace
cosines, observed norm changes, hook trigger counts and factor hashes are in
[`session014_hybrid_report.json`](experiments/session014_hybrid_report.json),
[`session014_hybrid_predictions.json`](experiments/session014_hybrid_predictions.json)
and reversible [`session014_orthogonal_factors.safetensors`](experiments/session014_orthogonal_factors.safetensors).
Reference-vector independence is numerical, not a guarantee that model behaviors
are causally disentangled. Reproducing gains requires genuinely external tests.

"""
    original = readme.read_text(encoding="utf-8")
    original = re.sub(r"\n<!-- SESSION014-PENDING-START -->.*?<!-- SESSION014-PENDING-END -->\n",
                      "\n", original, flags=re.DOTALL)
    if "## Session 014 —" in original:
        raise ValueError("Session014 README metrics already present")
    first,remainder = original.split("\n",1)
    if not first.startswith("# "):
        raise ValueError("Unrecognized repository README")
    readme.write_text(first+"\n\n"+fragment+remainder.lstrip("\n"),encoding="utf-8")
    print(json.dumps({track:comparisons[track]["overall"]["execution_passes"] for track in TRACKS}))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tracks-dir",type=Path,required=True)
    p.add_argument("--prepared-dir",type=Path,required=True)
    p.add_argument("--experiments-dir",type=Path,default=Path("experiments"))
    p.add_argument("--readme",type=Path,default=Path("README.md"))
    args=p.parse_args()
    collect(args.tracks_dir,args.prepared_dir,args.experiments_dir,args.readme)


if __name__=="__main__":
    main()
