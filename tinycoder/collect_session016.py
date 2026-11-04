"""Verify and publish adaptive 0.5B CPU search against archived Session015 control."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .rome20 import save_json
from .session014 import measure
from .session015 import MODEL_ID, MODEL_PARAMETER_COUNT
from .session016 import TRACKS


def collect(root:Path,out:Path,readme:Path):
    baseline=json.loads(Path("experiments/session015_gated_report.json").read_text())
    baseline_predictions=json.loads(Path("experiments/session015_gated_predictions.json").read_text())
    if baseline.get("status")!="completed" or baseline["model"]!=MODEL_ID:
        raise ValueError("Missing archived, measured Session015 control")
    manifest=baseline["dataset_manifest"]
    ids=manifest["mbpp_task_ids"]+manifest["web_task_ids"]
    if [x["task_id"] for x in baseline_predictions["baseline"]]!=ids:
        raise ValueError("Archived control predictions do not match manifest")

    comparisons={"baseline":baseline["comparisons"]["baseline"]}
    winners={}
    budgets={}
    for name in TRACKS:
        report=json.loads((root/f"session016-track-{name}"/"report.json").read_text())
        predictions=json.loads((root/f"session016-track-{name}"/"predictions.json").read_text())
        if (report["status"]!="completed" or report["track"]!=name
                or report["model"]!=MODEL_ID
                or report["parameter_count"]!=MODEL_PARAMETER_COUNT
                or report["training_steps"]!=0
                or report["manifest"]!=manifest
                or [p["task_id"] for p in predictions]!=ids
                or [p["task_id"] for p in report["task_results"]]!=ids
                or len(report["candidate_records"])!=100):
            raise ValueError(f"Benchmark integrity check failed on {name}")
        for label,subset in [
            ("mbpp_plus",report["task_results"][:50]),
            ("react_ui",report["task_results"][50:75]),
            ("express_backend",report["task_results"][75:]),
            ("overall",report["task_results"])]:
            if report[label]!=measure(subset):
                raise ValueError(f"Non-reproducible {label} score for {name}")
        if report["selection"]["plus_test_leakage"] is not False:
            raise ValueError("Invalid selection privacy assertion")
        comparisons[name]={k:report[k] for k in ("mbpp_plus","react_ui","express_backend","overall","selection","generation")}
        winners[name]=predictions
        budgets[name]={
            "output_tokens":report["generation"]["generated_output_tokens"],
            "elapsed_seconds":report["generation"]["wall_seconds"],
            "public_passes":report["selection"]["public_passes"],
            "winning_source_counts":report["selection"]["winning_source_counts"],
        }
    report={
        "status":"completed","session":"016",
        "branch":"exp/14-execution-guided-search",
        "model":MODEL_ID,"parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
        "manifest":manifest,"tracks":comparisons,
        "baseline_provenance":"Session015 greedy control, same frozen 100 prompts and 160-token decoding; no extra baseline inference",
        "fairness":"Only original MBPP public test_list guides selection, never EvalPlus expanded plus-input or canonical solution. Web public smoke tests are derived from fixture specs, with unavoidable overlap on constant/boolean behavior. All final assertions run in Docker.",
        "metric_note":"Selected system-level solve@1 uses multiple inference calls; it is NOT single-sample model pass@1. Do not compare to baseline without noting additional inference budget.",
        "compute":budgets,
        "predictions":"experiments/session016_search_predictions.json",
        "candidate_archives":"GitHub Actions artifacts session016-track-{search2,search4}, each includes complete candidate_records and public/final test results",
    }
    out.mkdir(parents=True,exist_ok=True)
    save_json(out/"session016_search_report.json",report)
    save_json(out/"session016_search_predictions.json",winners)
    lines=[]
    for name in ("baseline",*TRACKS):
        r=comparisons[name]
        py,ui,api,allr=(r[x] for x in ("mbpp_plus","react_ui","express_backend","overall"))
        token="reused" if name=="baseline" else str(budgets[name]["output_tokens"])
        lines.append(f"| {name} | {py['execution_passes']}/50 | {ui['execution_passes']}/25 | "
                     f"{api['execution_passes']}/25 | {allr['execution_passes']}/100 | "
                     f"{allr['syntax_valid']}/100 | {token} |")
    old=readme.read_text(encoding="utf-8")
    start="<!-- SESSION016-PENDING-START -->"
    end="<!-- SESSION016-PENDING-END -->"
    if start not in old or end not in old:
        raise ValueError("Missing Session016 pending section")
    fragment="""## Session 016 — adaptive execution-guided search (measured)

Same **Qwen2.5-Coder-0.5B base**, no trained/editable parameters. The
Session015 untouched 100-task greedy control is reused exactly, saving compute
and preserving the same test inputs. The searched variants begin with greedy
plus one sampled solution, run original MBPP public assertions or independently
derived web smoke tests, then optionally sample additional solutions
(`search4`) and attempt one error-conditioned repair. Extra sampling stops
after public validation succeeds. Final MBPP+ expanded tests are never used
for candidate selection.

| Variant | MBPP+ execution | React execution | Express execution | Overall selected solve@1 | Syntax valid | New output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""+"\n".join(lines)+""" 

These are **system-level** final-selection results after additional compute,
not comparable single-sample model pass@1. Original MBPP public tests are
available to the search procedure; hidden EvalPlus plus inputs and canonical
solutions remain inaccessible. React/Express tests are custom specifications,
not independent third-party benchmarks; public smoke checks can necessarily
overlap semantically with the final tests for constant-return and Boolean tasks.

Read the [verified report](experiments/session016_search_report.json) and
[all final task-level predictions](experiments/session016_search_predictions.json).
Candidate-level records are available in the workflow artifacts.

"""
    prefix,tail=old.split(start,1)
    _,suffix=tail.split(end,1)
    readme.write_text(prefix+fragment+suffix.lstrip("\n"),encoding="utf-8")
    print(json.dumps({k:{"total":v["overall"]["execution_passes"],
                          "python":v["mbpp_plus"]["execution_passes"],
                          "ui":v["react_ui"]["execution_passes"],
                          "api":v["express_backend"]["execution_passes"]}
                      for k,v in comparisons.items()}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,default=Path("experiments"))
    p.add_argument("--readme",type=Path,default=Path("README.md"))
    args=p.parse_args()
    collect(args.root,args.output_dir,args.readme)


if __name__=="__main__":
    main()
