"""Reconstruct all gated-versus-ungated metrics from actual 100-task results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .session014 import measure
from .session015 import (EXPECTED_FACTOR_SHA256, MODEL_ID,
                         MODEL_PARAMETER_COUNT, TRACKS)


def collect(tracks_root: Path, out: Path, readme: Path):
    from .rome20 import save_json
    reports,predictions={},{}
    for track in TRACKS:
        path=tracks_root/f"session015-track-{track}"
        r=json.loads((path/"report.json").read_text(encoding="utf-8"))
        p=json.loads((path/"predictions.json").read_text(encoding="utf-8"))
        manifest=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
        ids=manifest["mbpp_task_ids"]+manifest["web_task_ids"]
        if (r["status"]!="completed" or r["track"]!=track or r["model"]!=MODEL_ID
                or r["parameter_count"]!=MODEL_PARAMETER_COUNT or r["training_steps"]!=0
                or r["factor_sha256"]!=EXPECTED_FACTOR_SHA256 or r["manifest"]!=manifest
                or len(ids)!=100 or len(set(ids))!=100 or len(p)!=100
                or [x["task_id"] for x in p]!=ids
                or [x["task_id"] for x in r["task_results"]]!=ids):
            raise ValueError(f"Incomplete or inconsistent track {track}")
        for label,subset in (("mbpp_plus",r["task_results"][:50]),
                             ("react_ui",r["task_results"][50:75]),
                             ("express_backend",r["task_results"][75:]),
                             ("web_combined",r["task_results"][50:]),
                             ("overall",r["task_results"])):
            if r[label]!=measure(subset):
                raise ValueError(f"Irreproducible {track} {label} metrics")
        classifications=[r["mode_detector"][k]["mode"] for k in ids]
        if classifications!=["baseline"]*50+["ui"]*25+["backend"]*25:
            raise ValueError("Prompt-based classifier changed across experiment")
        if not r["baseline_weights_unchanged_by_hooks"]:
            raise ValueError("Runtime hooks changed stored weights")
        if track=="baseline" and (r["configuration"]["multiplier"] is not None and
                                   r["configuration"]["name"]!="baseline"):
            raise ValueError("Untouched baseline has an edit")
        if track=="ungated" and set(r["static_relative_norms"])!={"layer8","layer16"}:
            raise ValueError("Ungated static comparator omitted factors")
        if track.startswith("gated") and r["static_relative_norms"]:
            raise ValueError("Gated run unexpectedly mutated a model weight")
        reports[track],predictions[track]=r,p
    reference_manifest=reports["baseline"]["manifest"]
    if any(r["manifest"]!=reference_manifest for r in reports.values()):
        raise ValueError("Some tracks evaluated a different frozen task set")
    baseline={p["task_id"]:p["completion"] for p in predictions["baseline"]}
    comparisons={}
    for track in TRACKS:
        r=reports[track]
        current={p["task_id"]:p["completion"] for p in predictions[track]}
        unchanged={
            "python":all(current[k]==baseline[k] for k in reference_manifest["mbpp_task_ids"]),
            "ui":all(current[k]==baseline[k] for k in reference_manifest["web_task_ids"][:25]),
            "api":all(current[k]==baseline[k] for k in reference_manifest["web_task_ids"][25:]),
        }
        if track=="gated-0.0" and not all(unchanged.values()):
            raise ValueError("Zero-gate output is not an exact baseline reproduction")
        if track.startswith("gated") and not unchanged["python"]:
            raise ValueError("Python was modified despite an explicit zero gate")
        if track=="gated-ui-only-1.0" and not unchanged["api"]:
            raise ValueError("UI-only ablation unexpectedly modified API output")
        success={
            "old_absolute_targets":{
                "python_at_least_27":r["mbpp_plus"]["execution_passes"]>=27,
                "ui_at_least_7":r["react_ui"]["execution_passes"]>=7,
                "api_at_least_1":r["express_backend"]["execution_passes"]>=1,
            },
            "same_task_baseline_preserved":{
                "python":r["mbpp_plus"]["execution_passes"]>=reports["baseline"]["mbpp_plus"]["execution_passes"],
                "api":r["express_backend"]["execution_passes"]>=reports["baseline"]["express_backend"]["execution_passes"],
            },
        }
        comparisons[track]={
            "mbpp_plus":r["mbpp_plus"],"react_ui":r["react_ui"],
            "express_backend":r["express_backend"],"overall":r["overall"],
            "configuration":r["configuration"],
            "exact_completions_equal_to_untouched_baseline":unchanged,
            "forward_prehook_calls":r["forward_prehook_calls"],
            "criteria":success,
            "failure_taxonomy_shift":{label:{
                "baseline":reports["baseline"]["overall"]["failure_bins"].get(label,0),
                "track":r["overall"]["failure_bins"].get(label,0)}
                for label in sorted(set(reports["baseline"]["overall"]["failure_bins"]) |
                                    set(r["overall"]["failure_bins"]))},
        }
    report={
        "status":"completed","session":"015","branch":"exp/13-context-gated-subspaces",
        "model":MODEL_ID,"parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
        "factor_sha256":EXPECTED_FACTOR_SHA256,
        "factor_source":"Session014, frozen and SHA256 verified; direct rank32 low-rank factors",
        "dataset_manifest":reference_manifest,
        "tested_tracks":list(TRACKS),"comparisons":comparisons,
        "success_interpretation":"The old 27/7/1 targets were obtained on a DIFFERENT 100-task suite. Exact output preservation and concurrent task-matched pass scores are stronger evidence than raw target counts.",
        "execution":"50 EvalPlus MBPP+ tasks with expanded tests + 25 custom React and 25 custom Express tasks, all tested in Docker",
        "limitations":"The web tasks are newly numbered variants from the same five-family templates; they are not independent third-party web benchmarks. No guarantee against pretraining contamination. Baseline-equivalent code is checked exactly on frozen prompts, not universally across all Python or API prompts.",
        "raw_predictions_file":"experiments/session015_gated_predictions.json",
    }
    out.mkdir(parents=True,exist_ok=True)
    save_json(out/"session015_gated_report.json",report)
    save_json(out/"session015_gated_predictions.json",predictions)

    def score(track,name):
        r=reports[track][name]
        return f"{r['execution_passes']}/{r['count']}"
    lines=[]
    for track in TRACKS:
        r=reports[track]
        lines.append(f"| {track} | {score(track,'mbpp_plus')} | {score(track,'react_ui')} | "
                     f"{score(track,'express_backend')} | {r['overall']['execution_passes']}/100 | "
                     f"{r['overall']['syntax_valid']}/100 | "
                     f"{'Yes' if comparisons[track]['exact_completions_equal_to_untouched_baseline']['python'] else 'No'} |")
    fragment="""## Session 015 — context-gated orthogonal subspaces (measured)

This experiment uses only the original Qwen2.5-Coder-0.5B base checkpoint
and the **exact** Session014 rank32 factor file (SHA-256-verified). No
optimization or training occurs. Static edits use in-memory weight changes;
conditional edits use two `register_forward_pre_hook` and paired forward
hooks, such that `W@X + M*(Left@Right)@X` is computed without changing `W`.

The **100 new task prompts** are 50 MBPP+ test-split problems excluding
all 150 previously consumed MBPP problems from Sessions013/014, plus 25
new React and 25 new Express task variants from the custom fixture families.
The web templates are not a public standardized benchmark. Mode selection
uses lexical prompt triggers exclusively; Python defaults to zero mask.

| Evaluation track | MBPP+ pass@1 (50) | React pass@1 (25) | Express pass@1 (25) | Total pass@1 | Syntax valid | Python exactly baseline? |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""+"\n".join(lines)+"\n\n"+"""The explicit backend gate activates the Session014 Layer16 backend factor;
the separate `gated-ui-only-1.0` ablation intentionally disables it to
test whether this prevents the Express regression.

The former absolute targets (27/50 Python, 7/25 React, 1/25 Express)
refer to a **different** evaluation sample and are not assumed to hold on
fresh tasks. Strict Python/API preservation requires comparing identical
prompts and outputs against this session's untouched baseline.

See the [full per-task report](experiments/session015_gated_report.json)
and [task-level predictions](experiments/session015_gated_predictions.json).
The original [reversible factors](https://github.com/7clan/ai-wieght-optimiization/blob/exp/12-hybrid-ortho-hooks/experiments/session014_orthogonal_factors.safetensors)
remain stored on the Session014 branch.

"""
    old=readme.read_text(encoding="utf-8")
    old=re.sub(r"\n<!-- SESSION015-PENDING-START -->.*?<!-- SESSION015-PENDING-END -->\n",
               "\n",old,flags=re.DOTALL)
    if "## Session 015 —" in old:
        raise ValueError("Session015 measured README already present")
    first,rest=old.split("\n",1)
    readme.write_text(first+"\n\n"+fragment+rest.lstrip("\n"),encoding="utf-8")
    print(json.dumps({track:{"mbpp":reports[track]["mbpp_plus"]["execution_passes"],
                              "react":reports[track]["react_ui"]["execution_passes"],
                              "api":reports[track]["express_backend"]["execution_passes"]}
                      for track in TRACKS}))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tracks-root",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,default=Path("experiments"))
    p.add_argument("--readme",type=Path,default=Path("README.md"))
    args=p.parse_args()
    collect(args.tracks_root,args.output_dir,args.readme)


if __name__=="__main__":
    main()
