"""Deterministically assemble candidate modules as inspectable app projects.

The generated source is UNTRUSTED. These exports are archival artifacts; never
run generated projects on the host. Docker evaluation happens separately.
"""
from __future__ import annotations

import json
from pathlib import Path


def export_project(root: Path, task: dict, sources: dict, *, holdout_passed: bool):
    slug = task["contract"]["slug"]
    app = root / slug
    for folder in ("backend", "server", "client/src"):
        (app / folder).mkdir(parents=True, exist_ok=True)

    def put(path, content):
        (app / path).write_text(content, encoding="utf-8")

    put("contract.json", json.dumps(task["contract"], indent=2) + "\n")
    put("backend/logic.py", sources["logic"])
    put("backend/bridge.py", '''"""Trusted JSON-in/JSON-out CLI adapter for the generated function."""
import json
import sys
from logic import transform

data = json.load(sys.stdin)
json.dump(transform(data), sys.stdout, allow_nan=False)
''')
    put("server/index.js", sources["api"] + "\nmodule.exports = createApp;\n")
    put("server/main.js", '''// Trusted Express-to-Python adapter; generated code only in index.js.
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const express = require('express');
const createApp = require('./index');
function processor(data) {
  const child = spawnSync('python3', [path.join(__dirname,'../backend/bridge.py')], {
    input: JSON.stringify(data), encoding:'utf8', timeout:3000, maxBuffer:65536
  });
  if (child.error || child.status !== 0) throw Error(child.stderr || String(child.error));
  return JSON.parse(child.stdout);
}
const app = createApp(processor);
app.use(express.static(path.join(__dirname,'../client')));
app.listen(process.env.PORT || 3000);
''')
    put("client/src/ResultView.jsx", sources["ui"] + "\nexport default ResultView;\n")
    sample = json.dumps(task["public_cases"][0]["payload"])
    route = task["contract"]["route"]
    put("client/src/App.jsx", '''import React, {useEffect, useState} from 'react';
import ResultView from './ResultView';
export default function App() {
  const [data,setData] = useState(null);
  const [error,setError] = useState('');
  useEffect(() => {
    fetch(ROUTE, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(DEFAULT_INPUT)})
      .then(r => {if (!r.ok) throw Error('API failed'); return r.json();})
      .then(body => setData(body.data)).catch(e=>setError(String(e)));
  }, []);
  if (error) return <p role="alert">{error}</p>;
  return data ? <ResultView data={data}/> : <p>Loading...</p>;
}
'''.replace("ROUTE",json.dumps(route)).replace("DEFAULT_INPUT",sample))
    put("client/src/main.jsx", '''import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
createRoot(document.getElementById('root')).render(<App/>);
''')
    put("client/index.html", '''<!doctype html><html><head><meta charset="utf-8">
<title>Contract-first tiny app</title></head><body><div id="root"></div>
<script src="./dist/bundle.js"></script></body></html>
''')
    put("package.json", json.dumps({
        "name": f"tinycoder-{slug}", "private": True, "version": "0.0.1",
        "scripts": {"start": "node server/main.js",
                    "build": "esbuild client/src/main.jsx --bundle --outfile=client/dist/bundle.js --loader:.jsx=jsx"},
        "dependencies": {"express": "5.1.0", "react": "19.1.1", "react-dom": "19.1.1"},
        "devDependencies": {"esbuild": "0.25.9"}}, indent=2) + "\n")
    put("README.md", f"""# {slug}: archived candidate mini-app

Integrated holdout passed in sandbox: **{holdout_passed}**.

**WARNING:** Model-generated sources are untrusted. Do NOT execute this
archive outside an isolated container; even a passing unit-test fixture is
not a production security audit. The benchmark checks the modules and their
integration separately in network-disabled Docker.
""")
    return app
