"""Qwen0.5B owns all five PocketLedger module *bodies*, evaluated in Docker.

Fresh task domain, untouched model weights and bounded public feedback. The
trusted harness supplies only required file headers/signatures, dependencies,
execution tests and an isolated runtime. No hidden holdout values in prompts.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import html
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
from .session019_previews import sanitize_markup
from .session021 import generate_one
from .session027_contract import NAME, ROLES, PUBLIC, SPEC, fingerprint, holdout, prefix

IMAGE = "tinycoder-session027-autonomous:1"
MAX_NEW = {"logic":220,"store":650,"api":540,"ui":740,"css":340}
ROLE_PATHS = {"logic":"backend/logic.py","store":"server/store.js",
              "api":"server/routes.js","ui":"client/App.jsx","css":"client/style.css"}
BASE_SEED = 2026112700
MAX_REPAIR = 3


def evaluate(modules:dict, cases:list, phase:str, *, timeout=48)->dict:
    require_sandbox()
    if set(modules)!=set(ROLES) or phase not in ("public","holdout"):
        raise ValueError("Invalid module set or phase")
    with tempfile.TemporaryDirectory(prefix="qwen027-") as dirname:
        root=Path(dirname)
        inp,output=root/"input",root/"output"
        inp.mkdir(mode=0o755);output.mkdir(mode=0o777)
        os.chmod(root,0o755);os.chmod(output,0o777)
        req=inp/"input.json"
        req.write_text(json.dumps({"modules":modules,"cases":cases,"phase":phase}),encoding="utf-8")
        os.chmod(req,0o644)
        name="qwen027-"+uuid.uuid4().hex[:12]
        cmd=docker_command(IMAGE,inp,output,name,is_web=True)
        try:
            proc=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker","rm","-f",name],timeout=8,capture_output=True,check=False)
            return failure(phase,"Bounded Docker timeout")
        report=output/"result.json"
        if proc.returncode or not report.is_file():
            return failure(phase,"Docker evaluator error: "+proc.stderr[-260:])
        result=json.loads(report.read_text(encoding="utf-8"))
        if result.get("phase")!=phase or set(result.get("modules",{}))!=set(ROLES):
            raise RuntimeError("Docker evaluator identity mismatch")
        return result


def failure(phase:str,message:str)->dict:
    return {"phase":phase,"integrated":False,"completed_checks":0,"checks":{},
        "modules":{r:{"syntax_valid":False,"passed":False,"error":message} for r in ROLES},
        "failure_reasons":[message],"ui_markup":None}


def metric(report:dict,role:str)->tuple:
    details=report["modules"][role]
    return (int(details["passed"]),int(details["syntax_valid"]),
            int(report["completed_checks"]))


def feedback_prompt(role:str,previous:str,error:str)->str:
    """Teacher explains an observed failure, never writes the replacement code."""
    comment="# " if role=="logic" else "/* " if role=="css" else "// "
    trailer=" */" if role=="css" else ""
    condensed=" ".join(str(error or "Public contract not met").split())[:220]
    note=(comment+"PUBLIC TEST FAILED: "+condensed+trailer+"\n"+
          comment+"Mentor: inspect the required response shape, method names, "+
          "and missing syntax; repair the implementation yourself."+trailer+"\n")
    # Observed source is a prior *student attempt*; it is never a teacher solution.
    excerpts="\n".join(comment+line[:160]+trailer for line in previous[-1200:].splitlines()[-18:])
    return note+excerpts+"\n"+prefix(role,mentor=True)


def preview(modules:dict,public:dict,hold:dict,output:Path)->None:
    safe=sanitize_markup(hold.get("ui_markup") or public.get("ui_markup") or "")
    if not safe.strip():
        safe="<p>Qwen's React component could not render in the isolated test.</p>"
    badges="".join(f'<span class="badge {"pass" if hold["modules"][r]["passed"] else "fail"}">'
                   f'{r.upper()}: {"PASS" if hold["modules"][r]["passed"] else "FAIL"}</span>'
                   for r in ROLES)
    sources="".join('<details><summary>'+html.escape(ROLE_PATHS[r])+'</summary><pre>'+
                    html.escape(modules[r])+'</pre></details>' for r in ROLES)
    failures="".join("<li>"+html.escape(e)+"</li>" for e in hold["failure_reasons"])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Qwen0.5B independently completed PocketLedger modules</title>
<style>*{box-sizing:border-box}body{background:#0d1527;color:#e3ecf8;font:15px system-ui;margin:0}
main{max-width:1100px;margin:55px auto;padding:20px}h1{font-size:42px;letter-spacing:-.04em}
p{color:#a5b8d2;line-height:1.6}.badges{display:flex;flex-wrap:wrap;gap:9px;margin:25px 0}
.badge{padding:8px 12px;border-radius:18px;background:#3b475b;font-weight:800;font-size:12px}
.pass{background:#16493b;color:#a7f4dc}.fail{background:#5b293b;color:#ffc9d3}
.panel,details{border:1px solid #31445d;background:#162238;border-radius:15px;padding:22px;margin:18px 0}
.render{background:#f8fafc;color:#172341;border-radius:10px;padding:30px;overflow:auto;min-height:150px}
.render input,.render button{margin:8px;padding:7px}summary{cursor:pointer;font-weight:800}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}a{color:#8fe3f3}</style></head>
<body><main><h1>PocketLedger, actually written by Qwen?</h1>
<p>These are the real five model-completed modules from a fresh expense-tracker task.
The supervising agent supplied only required signatures, testing and execution tools,
not application logic. This safe source viewer is static and script-free; it is not
a deployed Express application or proof of production readiness.</p>
<div class="badges">'''+badges+'''</div>
<section class="panel"><h2>Actual React server-rendered markup</h2><div class="render">'''+safe+
'''</div></section><section class="panel"><h2>Independent holdout</h2><p>'''+
("Integrated PASS" if hold["integrated"] else "Integrated FAIL")+'''</p><ul>'''+failures+
'''</ul></section>'''+sources+
'''<p>No model-generated JavaScript runs in your browser. All execution occurred
inside short-lived, network-disabled, unprivileged Docker containers.</p></main></body></html>''',
        encoding="utf-8")


def run(args)->None:
    require_sandbox()
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite prior generated outputs")
    out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    model,tokenizer=_torch_model()
    param_count=sum(p.numel() for p in model.parameters())
    if param_count!=MODEL_PARAMETER_COUNT:
        raise RuntimeError("Unexpected Qwen checkpoint")
    model_outputs={}
    records=[]
    tokens=0
    for i,role in enumerate(ROLES):
        head=prefix(role)
        raw,n=generate_one(model,tokenizer,head,max_tokens=MAX_NEW[role],
                           seed=BASE_SEED+i,stochastic=False)
        model_outputs[role]=head+raw
        records.append({"stage":"greedy","role":role,"prompt":head,"raw":raw,"output_tokens":n})
        tokens+=n
        print("Qwen greedy",role,"tokens",n,flush=True)
    base=dict(model_outputs)
    baseline_public=evaluate(base,PUBLIC,"public")
    current=baseline_public
    print("Greedy module passes", {r:current["modules"][r]["passed"] for r in ROLES},flush=True)

    for attempt in range(MAX_REPAIR):
        for i,role in enumerate(ROLES):
            if current["modules"][role]["passed"]:
                continue
            previous=model_outputs[role]
            query=(prefix(role,mentor=True) if attempt==0 else
                   feedback_prompt(role,previous,current["modules"][role]["error"]))
            raw,n=generate_one(model,tokenizer,query,max_tokens=MAX_NEW[role],
                               seed=BASE_SEED+50+attempt*13+i,stochastic=True)
            tokens+=n
            candidate=dict(model_outputs)
            candidate[role]=prefix(role)+raw
            observed=evaluate(candidate,PUBLIC,"public")
            accepted=metric(observed,role)>metric(current,role)
            records.append({"stage":"mentor-sample" if attempt==0 else "student-repair",
                            "role":role,"attempt":attempt,"prompt":query,"raw":raw,
                            "output_tokens":n,"accepted":accepted,
                            "error":observed["modules"][role]["error"],
                            "module_passed":observed["modules"][role]["passed"]})
            if accepted: model_outputs,current=candidate,observed
            print("Qwen",role,"attempt",attempt,"PASS" if observed["modules"][role]["passed"]
                  else "FAIL", "accepted" if accepted else "rejected",flush=True)
    del model
    gc.collect()

    # Select only against PUBLIC feedback. Load holdout *after* every candidate.
    baseline_holdout=evaluate(base,holdout(),"holdout")
    selected_holdout=evaluate(model_outputs,holdout(),"holdout")
    selected_public=evaluate(model_outputs,PUBLIC,"public")
    report={
        "session":"027","status":"completed","model":MODEL_ID,
        "parameter_count":param_count,"training_steps":0,"weight_edits":0,
        "app":NAME,"contract_sha256":fingerprint(),"model_completed_roles":list(ROLES),
        "trusted_authored_code":["minimal source signatures/imports in prefixes",
          "Docker evaluator","dependency harness","test-only positive controls",
          "React server-side renderer","static preview generator"],
        "baseline":{"public":baseline_public,"holdout":baseline_holdout},
        "selected":{"public":selected_public,"holdout":selected_holdout},
        "search":{"candidate_count":len(records),"output_tokens":tokens,
                  "wall_seconds":round(time.monotonic()-started,2),
                  "max_guided_attempts_per_role":MAX_REPAIR,
                  "private_holdout_seen_during_selection":False},
        "attribution":"Qwen completed all five file bodies; evaluator authored signatures and imports. No application module was replaced with a teacher-authored solution.",
        "new_app_not_seen_in_prior_sessions":True,
        "independent_model_authorship_of_build_infrastructure":False,
        "browser_clicks_verified":False,
        "production_ready":False
    }
    save_json(out/"report.json",report)
    save_json(out/"predictions.json",{
        "prefixes":{r:prefix(r) for r in ROLES},"greedy":base,
        "selected":model_outputs,"attempts":records,
        "public_spec":SPEC,"source_sha256":{r:hashlib.sha256(model_outputs[r].encode()).hexdigest() for r in ROLES}})
    for role,p in ROLE_PATHS.items():
        dest=out/"generated"/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(model_outputs[role],encoding="utf-8")
    preview(model_outputs,selected_public,selected_holdout,out/"preview"/"index.html")
    print(json.dumps({"baseline_holdout":baseline_holdout["integrated"],
                      "selected_holdout":selected_holdout["integrated"],
                      "modules":{r:v["passed"] for r,v in selected_holdout["modules"].items()},
                      "count":len(records)}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir",default="outputs/session027")
    run(p.parse_args())


if __name__=="__main__":
    main()
