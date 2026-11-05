"""Provenance audit and package verified teacher-corrected PocketLedger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session027 import ROLE_PATHS
from .session027_contract import ROLES
from .session029_teacher import STORE, API, UI


MAIN_CJS="""'use strict';
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const express=require('express');
const {createStore}=require('./store.js');
const {createApp}=require('./routes.js');
const db=process.env.POCKETLEDGER_DB || path.join(__dirname,'../data/expenses.json');
require('node:fs').mkdirSync(path.dirname(db),{recursive:true});
const processor=payload=>{
 const result=spawnSync('python3',['-I','-B',path.join(__dirname,'../backend/bridge.py')],{
  input:JSON.stringify(payload),encoding:'utf8',timeout:3000,maxBuffer:1024*1024
 });
 if(result.error || result.status!==0)throw new Error(result.error?.message || result.stderr);
 return JSON.parse(result.stdout);
};
const app=createApp(createStore(db),processor);
app.use(express.static(path.join(__dirname,'../public')));
const port=Number(process.env.PORT || 3000);
app.listen(port,'0.0.0.0',()=>console.log('PocketLedger running at http://localhost:'+port));
"""

BRIDGE_PY="""import json
from pathlib import Path
import runpy
import sys

transform = runpy.run_path(str(Path(__file__).with_name('logic.py')))['transform']
request = json.loads(sys.stdin.read())
print(json.dumps(transform(request)))
"""

HTML="""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PocketLedger</title><link rel="stylesheet" href="/style.css"></head>
<body><div id="root"></div><script src="/app.js" defer></script></body></html>
"""
ENTRY="""const React=require('react');
const {createRoot}=require('react-dom/client');
const {App}=require('./App.jsx');
createRoot(document.getElementById('root')).render(React.createElement(App));
"""
PKG={"name":"pocketledger-qwen-mentored","version":"0.1.0","private":True,
     "scripts":{"build":"esbuild client/main.jsx --bundle --platform=browser --format=iife --outfile=public/app.js",
                "start":"npm run build && node server/main.cjs"},
     "dependencies":{"esbuild":"0.25.9","express":"5.1.0",
                     "react":"19.1.1","react-dom":"19.1.1"}}

README="""# PocketLedger: Qwen + teacher corrections

**Full-stack application. Not Qwen-only.** The Python calculation and CSS are
exact model-generated source from Session028. An agent teacher rewrote Node JSON
storage, Express routes and the React client after inspecting Qwen's failures.
The adapter files, build command and Python-to-Express bridge are trusted tools.

Session029 verifies full CRUD persistence, API envelopes, Python aggregation,
and server-rendered React plus event/fetch source wiring using isolated Docker.
It **does not** prove a real browser click path or production security.

## Try the app in your own Codespace

Requires Node.js 22+ and Python 3.11+. In this directory:

```bash
npm install
npm start
```

Open port **3000** using Codespaces' **Ports** tab (keep private).
Try adding an expense, reloading the page, checking category totals, deleting
it, and reloading again.

To run the API smoke test from another terminal:

```bash
curl http://localhost:3000/api/expenses
curl http://localhost:3000/api/summary
```

This is a user-operated development build. Generated app source was *not*
executed outside restricted Docker by the experiment runners. Review it
before exposing any port. Never assume a Codespaces URL is a public deployment.
"""


def package_app(source:dict,root:Path):
    files={
      "backend/logic.py":source["logic"],
      "backend/bridge.py":BRIDGE_PY,
      "server/store.js":source["store"]+"\nmodule.exports={createStore};\n",
      "server/routes.js":source["api"]+"\nmodule.exports={createApp};\n",
      "server/main.cjs":MAIN_CJS,
      "client/App.jsx":source["ui"],
      "client/main.jsx":ENTRY,
      "public/index.html":HTML,
      "public/style.css":source["css"],
      "package.json":json.dumps(PKG,indent=2)+"\n",
      "README.md":README
    }
    for p,body in files.items():
        target=root/p
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(body,encoding="utf-8")


def collect(root:Path):
    report=json.loads((root/"report.json").read_text(encoding="utf-8"))
    data=json.loads((root/"corrections.json").read_text(encoding="utf-8"))
    assert report["session"]=="029" and report["teacher_rewritten_roles"]==["store","api","ui"]
    assert report["qwen_unchanged_roles"]==["logic","css"]
    assert report["model_full_app_success_claim"] is False
    assert report["teacher_corrected"]["public"]["integrated"]
    assert report["teacher_corrected"]["holdout"]["integrated"]
    original=json.loads(Path("experiments/session028_mentor_predictions.json").read_text(encoding="utf-8"))
    source=data["after"]
    if set(source)!=set(ROLES) or source["logic"]!=original["selected"]["logic"] or source["css"]!=original["selected"]["css"]:
        raise ValueError("Qwen modules were altered")
    if source["store"]!=STORE or source["api"]!=API or source["ui"]!=UI:
        raise ValueError("Teacher correction sources changed")
    for role,p in ROLE_PATHS.items():
        if (root/"generated"/p).read_text(encoding="utf-8")!=source[role]:
            raise ValueError("Source/archive mismatch")
    page=(root/"preview/index.html").read_text(encoding="utf-8").lower()
    if "<script" in page or "<iframe" in page or "<form" in page:
        raise ValueError("Unsafe generated-source preview")

    gallery=Path("docs/previews/session029")
    if gallery.exists() and any(gallery.iterdir()):
        raise FileExistsError("Existing published preview")
    gallery.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/"preview/index.html",gallery/"index.html")
    for role,p in ROLE_PATHS.items():
        dest=gallery/"generated"/p
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/"generated"/p,dest)
    save_json(Path("experiments/session029_teacher_report.json"),report)
    save_json(Path("experiments/session029_correction_pairs.json"),data)
    package_app(source,Path("apps/pocketledger-qwen-mentored"))
    print("PASS: verified teacher-assisted PocketLedger packaged",flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,default=Path("outputs/session029"))
    collect(p.parse_args().output_dir)


if __name__=="__main__":
    main()
