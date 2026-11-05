"""Verify Qwen-only target-source attribution before publishing transfer results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session030_contract import PREFIX, ROLES, fingerprint


def collect(root:Path):
    report=json.loads((root/"report.json").read_text(encoding="utf8"))
    pred=json.loads((root/"predictions.json").read_text(encoding="utf8"))
    if (report.get("session")!="030" or report.get("status")!="completed" or
        report.get("model")!=MODEL_ID or report.get("parameter_count")!=MODEL_PARAMETER_COUNT or
        report.get("training_steps")!=0 or report.get("weight_edits")!=0 or
        report.get("contract_sha256")!=fingerprint() or
        report.get("target_app_modules_from_qwen")!=list(ROLES) or
        report.get("teacher_supplied_exact_target_solutions") is not False or
        report["search"]["private_holdout_seen_during_selection"] is not False):
        raise ValueError("Invalid frozen-model experiment provenance")
    attempts=pred["attempts"]
    if report["search"]["candidate_count"]!=len(attempts) or len(attempts)<len(ROLES):
        raise ValueError("Candidate count does not match raw generations")
    if [(x["stage"],x["role"]) for x in attempts[:5]]!=[("baseline",r) for r in ROLES]:
        raise ValueError("Missing actual student greedy baseline")
    if set(pred["selected"])!=set(ROLES) or set(pred["greedy"])!=set(ROLES):
        raise ValueError("Incomplete generated model sources")
    for role in ROLES:
        source=pred["selected"][role]
        options=[PREFIX[role]+x["raw"] for x in attempts if
                 x["role"]==role and (x["stage"]=="baseline" or x.get("accepted"))]
        if source not in options or not source.startswith(PREFIX[role]):
            raise ValueError("Non-model target code substituted: "+role)
        if (root/"generated"/ROLE_PATHS[role]).read_text(encoding="utf8")!=source:
            raise ValueError("Saved file changed from Qwen raw candidate: "+role)
    for track in ("baseline","guided"):
        for phase in ("public","holdout"):
            result=report[track][phase]
            if result["phase"]!=phase or set(result["modules"])!=set(ROLES):
                raise ValueError("Mismatch in evaluation identity")
            if result["integrated"] and not (
               all(x["passed"] for x in result["modules"].values()) and
               result["checks"].get("integration") is True and
               result["checks"].get("ui_wiring") is True):
                raise ValueError("Fabricated integrated success")
    page=(root/"preview/index.html").read_text(encoding="utf8").lower()
    if any(tag in page for tag in ("<script","<iframe","<form")):
        raise ValueError("Unsafe preview")
    dest=Path("docs/previews/session030")
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Preview already exists; not overwriting")
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/"preview/index.html",dest/"index.html")
    for role,path in ROLE_PATHS.items():
        p=dest/"generated"/path
        p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/"generated"/path,p)
    save_json(Path("experiments/session030_transfer_report.json"),report)
    save_json(Path("experiments/session030_transfer_predictions.json"),pred)
    print(json.dumps({"guided_integrated":report["guided"]["holdout"]["integrated"],
        "baseline_integrated":report["baseline"]["holdout"]["integrated"],
        "guided_roles":{k:v["passed"] for k,v in report["guided"]["holdout"]["modules"].items()},
        "candidate_count":len(attempts)}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,default=Path("outputs/session030"))
    collect(p.parse_args().output_dir)


if __name__=="__main__":
    main()
