"""Audit prompt provenance, bounded search, model-only source and honest report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session027_contract import ROLES
from .session028_contract import PREFIX, fingerprint


def validate(root):
    report=json.loads((root/"report.json").read_text(encoding="utf-8"))
    prediction=json.loads((root/"predictions.json").read_text(encoding="utf-8"))
    if (report.get("session")!="028" or report.get("status")!="completed"
        or report.get("model")!=MODEL_ID
        or report.get("parameter_count")!=MODEL_PARAMETER_COUNT
        or report.get("training_steps")!=0 or report.get("weight_edits")!=0
        or report.get("contract_sha256")!=fingerprint()
        or report.get("teacher_authored_target_app_modules")!=0
        or report.get("model_authored_module_bodies")!=list(ROLES)
        or report["search"]["private_holdout_seen_during_selection"] is not False):
        raise ValueError("Provenance or frozen contract mismatch")
    if report["search"]["candidate_count"]!=len(prediction["attempts"]):
        raise ValueError("Missing bounded candidate trace")
    if set(prediction["selected"])!=set(ROLES):
        raise ValueError("Incomplete model source")
    prior=prediction["previous"]
    for role in ROLES:
        source=prediction["selected"][role]
        if (source!=prior[role] and
            not any(x["role"]==role and x["accepted"] and
                    x["candidate_source"]==source for x in prediction["attempts"])):
            raise ValueError("Teacher-written substitution: "+role)
        if (role in PREFIX and source!=prior[role]
            and not source.startswith(PREFIX[role])):
            raise ValueError("Altered target signature: "+role)
        if (root/"generated"/ROLE_PATHS[role]).read_text(encoding="utf-8")!=source:
            raise ValueError("Archived output differs from student source")
    for track in ("baseline","selected"):
        for phase in ("public","holdout"):
            result=report[track][phase]
            if set(result.get("modules",{}))!=set(ROLES) or result["phase"]!=phase:
                raise ValueError("Bad evaluation schema")
            if result["integrated"] and not (
                all(result["modules"][r]["passed"] for r in ROLES)
                and result["checks"].get("integration") is True
                and result["checks"].get("ui_wiring") is True):
                raise ValueError("Invalid integrated score")
    doc=(root/"preview"/"index.html").read_text(encoding="utf-8").lower()
    if any(tag in doc for tag in ("<script","<iframe","<form")):
        raise ValueError("Unsafe static preview")
    return report,prediction


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,default=Path("outputs/session028"))
    root=p.parse_args().output_dir
    report,preds=validate(root)
    gallery=Path("docs/previews/session028")
    if gallery.exists() and any(gallery.iterdir()):
        raise FileExistsError("Refusing to overwrite prior preview")
    gallery.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/"preview"/"index.html",gallery/"index.html")
    for role,path in ROLE_PATHS.items():
        dest=gallery/"generated"/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/"generated"/path,dest)
    save_json(Path("experiments/session028_mentor_report.json"),report)
    save_json(Path("experiments/session028_mentor_predictions.json"),preds)
    print(json.dumps({"integrated":report["selected"]["holdout"]["integrated"],
        "checks":report["selected"]["holdout"]["checks"]}),flush=True)


if __name__=="__main__":
    main()
