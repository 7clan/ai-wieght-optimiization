"""Teacher demonstrates analogous debugging patterns; Qwen regenerates target code.

This is in-context adaptation, NOT neural-weight training or fine-tuning.
Generated modules execute only in network-disabled, nonroot, read-only Docker.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import MODEL_ID, _torch_model, docker_command
from .session015 import MODEL_PARAMETER_COUNT
from .session021 import generate_one
from .session027 import ROLE_PATHS, preview, failure
from .session027_contract import NAME, ROLES, PUBLIC
from .session028_contract import PREFIX, ROLE_GOAL, LESSONS, fingerprint, fresh_holdout, prompt

IMAGE="tinycoder-session028-mentored:1"
LIMITS={"logic":300,"store":650,"api":650,"ui":900}
SEED=2026112800


def evaluate(modules, cases, phase, *, timeout=50):
    require_sandbox()
    if set(modules)!=set(ROLES) or phase not in ("public","holdout"):
        raise ValueError("Invalid module set/phase")
    with tempfile.TemporaryDirectory(prefix="qwen028-") as dirname:
        root=Path(dirname)
        inp,output=root/"input",root/"output"
        inp.mkdir(mode=0o755); output.mkdir(mode=0o777)
        os.chmod(root,0o755); os.chmod(output,0o777)
        req=inp/"input.json"
        req.write_text(json.dumps({"modules":modules,"cases":cases,"phase":phase}),encoding="utf-8")
        os.chmod(req,0o644)
        name="qwen028-"+uuid.uuid4().hex[:12]
        try:
            proc=subprocess.run(docker_command(IMAGE,inp,output,name,is_web=True),
                                text=True,capture_output=True,timeout=timeout,check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker","rm","-f",name],capture_output=True,timeout=8,check=False)
            return failure(phase,"Bounded Docker timeout")
        p=output/"result.json"
        if proc.returncode or not p.exists():
            return failure(phase,"Docker evaluator error: "+proc.stderr[-240:])
        report=json.loads(p.read_text(encoding="utf-8"))
        if report.get("phase")!=phase or set(report.get("modules",{}))!=set(ROLES):
            raise RuntimeError("Docker evaluator protocol mismatch")
        return report


def score(report,role):
    item=report["modules"][role]
    scoped={"api":("get","post","summary","delete"),
            "store":("persistence","store_delete"),
            "ui":("ui_wiring",),"logic":()}[role]
    return (int(item["passed"]),sum(bool(report["checks"].get(k)) for k in scoped),
            int(item["syntax_valid"]))


def run(args):
    require_sandbox()
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite existing run")
    out.mkdir(parents=True,exist_ok=True)
    previous=json.loads(Path(args.prior_predictions).read_text(encoding="utf-8"))
    source=dict(previous["selected"])
    if set(source)!=set(ROLES):
        raise ValueError("Missing prior Qwen source")
    previous_sha={k:hashlib.sha256(v.encode()).hexdigest() for k,v in source.items()}
    started=time.monotonic()
    baseline_public=evaluate(source,PUBLIC,"public")
    current_public=baseline_public
    model,tokenizer=_torch_model()
    param_count=sum(p.numel() for p in model.parameters())
    if param_count!=MODEL_PARAMETER_COUNT:
        raise RuntimeError("Unexpected model checkpoint")
    records=[]
    tokens=0
    for level in range(3):
        for i,role in enumerate(("logic","store","api","ui")):
            if current_public["modules"][role]["passed"]:
                continue
            lesson=prompt(role,current_public["modules"][role]["error"],level)
            raw,n=generate_one(model,tokenizer,lesson,max_tokens=LIMITS[role],
                               seed=SEED+10*level+i,stochastic=level>0)
            tokens+=n
            candidate=dict(source)
            candidate[role]=PREFIX[role]+raw
            result=evaluate(candidate,PUBLIC,"public")
            improved=score(result,role)>score(current_public,role)
            records.append({
                "role":role,"teacher_stage":level,"teacher_rule":ROLE_GOAL[role],
                "analogy":LESSONS[role],"prior_error":current_public["modules"][role]["error"],
                "prompt":lesson,"raw":raw,"output_tokens":n,"accepted":improved,
                "candidate_source":candidate[role],
                "public_result":result["modules"][role],
                "role_score":list(score(result,role))
            })
            if improved:
                source,current_public=candidate,result
            print(json.dumps({"round":level,"role":role,"tokens":n,
                   "passed":result["modules"][role]["passed"],
                   "accepted":improved,"error":result["modules"][role]["error"]}),flush=True)
    del model
    gc.collect()

    # Fresh holdout is touched ONLY AFTER all Qwen candidate selection freezes.
    holdout_cases=fresh_holdout()
    baseline_hold=evaluate(previous["selected"],holdout_cases,"holdout")
    selected_hold=evaluate(source,holdout_cases,"holdout")
    selected_public=evaluate(source,PUBLIC,"public")
    report={
        "session":"028","status":"completed","model":MODEL_ID,
        "parameter_count":param_count,"training_steps":0,"weight_edits":0,
        "contract_sha256":fingerprint(),"app":NAME,
        "teaching":"analogous worked examples + observed errors; student-only target source",
        "first_model_run":"027","first_model_source_sha256":previous_sha,
        "teacher_authored_target_app_modules":0,
        "model_authored_module_bodies":list(ROLES),
        "greedy_replayed_from_session027":True,
        "baseline":{"public":baseline_public,"holdout":baseline_hold},
        "selected":{"public":selected_public,"holdout":selected_hold},
        "search":{"candidate_count":len(records),"output_tokens":tokens,
                  "wall_seconds":round(time.monotonic()-started,2),
                  "private_holdout_seen_during_selection":False,
                  "selection_public_only":True,
                  "max_teacher_guided_trials_per_failing_role":3},
        "ui_check_stronger_than_session027":True,
        "browser_clicks_verified":False,
        "production_ready":False,
        "model_weights_learned_permanently":False
    }
    save_json(out/"report.json",report)
    save_json(out/"predictions.json",{"previous":previous["selected"],
        "selected":source,"attempts":records,
        "source_sha256":{k:hashlib.sha256(v.encode()).hexdigest() for k,v in source.items()}})
    for role,p in ROLE_PATHS.items():
        dest=out/"generated"/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(source[role],encoding="utf-8")
    preview(source,selected_public,selected_hold,out/"preview"/"index.html")
    print(json.dumps({"baseline_integrated":baseline_hold["integrated"],
         "selected_integrated":selected_hold["integrated"],
         "module_passes":{k:v["passed"] for k,v in selected_hold["modules"].items()},
         "candidate_count":len(records)}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prior-predictions",
        default="experiments/session027_autonomous_app_predictions.json")
    p.add_argument("--output-dir",default="outputs/session028")
    run(p.parse_args())


if __name__=="__main__":
    main()
