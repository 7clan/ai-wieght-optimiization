"""Teacher repairs the Qwen app; score assisted and Qwen-only tracks separately."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import time

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session019_previews import sanitize_markup
from .session027 import ROLE_PATHS
from .session027_contract import NAME, PUBLIC, ROLES
from .session028 import evaluate
from .session028_contract import fresh_holdout
from .session029_teacher import STORE, API, UI, REASONING_RULES


def preview(modules,source_tags,hold,output):
    h=html.escape
    safe=sanitize_markup(hold.get("ui_markup") or "")
    badges="".join('<span class="badge '+('pass' if hold['modules'][r]['passed'] else 'fail')+'">'+
      h(r.upper())+': '+('PASS' if hold['modules'][r]['passed'] else 'FAIL')+
      ' ('+h(source_tags[r])+')</span>' for r in ROLES)
    sources="".join("<details><summary>"+h(ROLE_PATHS[r])+" — "+h(source_tags[r])+
       "</summary><pre>"+h(modules[r])+"</pre></details>" for r in ROLES)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>PocketLedger teacher-corrected app — exact source</title>
<style>*{box-sizing:border-box}body{background:#101a31;color:#edf3ff;font:15px system-ui;margin:0}
main{max-width:1050px;margin:50px auto;padding:20px}h1{font-size:40px}
p{color:#b8c8e0;line-height:1.6}.badges{display:flex;flex-wrap:wrap;gap:9px;margin:25px 0}
.badge{font-weight:700;padding:8px 12px;border-radius:15px;background:#4c5566;font-size:12px}
.pass{background:#12543c;color:#b5ffcf}.fail{background:#5d2738;color:#ffd6de}
section,details{background:#1a2a45;border:1px solid #344a6e;border-radius:12px;
padding:19px;margin:17px 0}.render{background:#fff;color:#172341;padding:26px;
border-radius:8px;overflow:auto}.render input,.render button{margin:7px;padding:8px}
summary{font-weight:700;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;
font-size:12px;line-height:1.6}a{color:#a4e8ff}</style></head>
<body><main><h1>PocketLedger — teacher-corrected</h1>
<p>This is a real full-stack SOURCE integration verified inside restricted Docker.
Qwen authored the Python summary and original CSS; the teacher rewrote storage,
Express and React after observing Qwen's failures. The test evidence is linked
alongside every file. No claim of independent 0.5B full-app success is made.
This safe source preview is static and scripts cannot run here.</p>
<div class="badges">'''+badges+'''</div><section><h2>Actual React markup</h2>
<div class="render">'''+safe+'''</div></section>
<section><h2>Verification</h2><p>Docker-integrated result: '''+
('PASS' if hold['integrated'] else 'FAIL')+'''</p></section>'''+sources+
'''<p>To interact with the live app, start the separate packaged app in an
environment you control after reviewing its generated and corrected files.
This website is not a running backend.</p></main></body></html>''',encoding="utf-8")


def run(args):
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite an earlier teacher experiment")
    out.mkdir(parents=True,exist_ok=True)
    prior=json.loads(Path(args.prior_predictions).read_text(encoding="utf-8"))
    base=prior["selected"]
    if set(base)!=set(ROLES):
        raise ValueError("Session028 model file set not complete")
    source=dict(base)
    source.update({"store":STORE,"api":API,"ui":UI})
    tags={r:("Qwen-only, unchanged" if r in ("logic","css") else
             "teacher correction, NOT Qwen-only") for r in ROLES}
    began=time.monotonic()
    qwen_public=evaluate(base,PUBLIC,"public")
    corrected_public=evaluate(source,PUBLIC,"public")
    private=fresh_holdout()   # No model selection occurs in this experiment.
    qwen_private=evaluate(base,private,"holdout")
    corrected_private=evaluate(source,private,"holdout")
    report={"session":"029","status":"completed","model":MODEL_ID,
      "parameter_count":MODEL_PARAMETER_COUNT,
      "student_inference_calls":0,"training_steps":0,"weight_edits":0,
      "qwen_only":{"public":qwen_public,"holdout":qwen_private},
      "teacher_corrected":{"public":corrected_public,"holdout":corrected_private},
      "qwen_unchanged_roles":["logic","css"],"teacher_rewritten_roles":["store","api","ui"],
      "authorship":tags,"model_full_app_success_claim":False,
      "ui_browser_clicks_verified":False,
      "holdout_disclosure":"2 novel nonempty cases plus 1 repeated public empty-list control",
      "wall_seconds":round(time.monotonic()-began,2)}
    save_json(out/"report.json",report)
    save_json(out/"corrections.json",{"app":NAME,"before":base,"after":source,
       "authorship":tags,"reasoning_rules":REASONING_RULES,
       "source_hashes":{r:hashlib.sha256(source[r].encode()).hexdigest() for r in ROLES}})
    for role,path in ROLE_PATHS.items():
        target=out/"generated"/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source[role],encoding="utf-8")
    preview(source,tags,corrected_private,out/"preview"/"index.html")
    print(json.dumps({"qwen_integrated":qwen_private["integrated"],
      "teacher_integrated":corrected_private["integrated"],
      "teacher_modules":{r:v["passed"] for r,v in corrected_private["modules"].items()},
      "failures":corrected_private["failure_reasons"]}),flush=True)
    if not corrected_private["integrated"] or not corrected_public["integrated"]:
        raise RuntimeError("Teacher correction failed; do NOT publish as working")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prior-predictions",
        default="experiments/session028_mentor_predictions.json")
    p.add_argument("--output-dir",default="outputs/session029")
    run(p.parse_args())


if __name__=="__main__":
    main()
