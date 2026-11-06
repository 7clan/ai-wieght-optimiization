// apps/taskflow-qwen/server.js — TRUSTED-SCAFFOLD server wiring.
// Serves the Qwen-authored store + api + logic modules and the built
// frontend.  No application logic lives here; every byte of application
// behavior comes from the Qwen-authored modules loaded below.
'use strict';
const path = require('node:path');
const fs = require('node:fs');
const express = require('express');
const { spawnSync } = require('node:child_process');

const ROOT = __dirname;
const DATA = process.env.TASKFLOW_DATA ||
  path.join(ROOT, 'data', 'tasks.json');
const PORT = Number(process.env.TASKFLOW_PORT || 4173);
const HOST = process.env.TASKFLOW_HOST || '127.0.0.1';

// Qwen-authored modules (written by the archagent integration step with
// recorded provenance in ORIGIN.json).
const createStore = require('./server/store.js');
const createApi = require('./server/api.js');

// Synchronous Python bridge: runs the Qwen-authored logic.py in an
// isolated `python3 -I -B` subprocess (no site imports, no bytecode, no
// network) per progress request.  TRUSTED-SCAFFOLD adapter; the
// computation itself is 100% Qwen-authored Python.
const BRIDGE = path.join(ROOT, 'bridge.py');
function processor(payload) {
  const p = spawnSync('python3', ['-I', '-B', BRIDGE], {
    input: JSON.stringify(payload),
    encoding: 'utf8',
    timeout: 5000,
    maxBuffer: 65536,
    env: {PYTHONDONTWRITEBYTECODE: '1', PYTHONHASHSEED: '0'},
  });
  if (p.error || p.status !== 0) {
    throw new Error('processor bridge failed: ' +
      (p.error ? p.error.message : String(p.stderr || '').slice(-200)));
  }
  return JSON.parse(p.stdout);
}

const app = express();
const store = createStore(DATA);
createApi(app, store, processor);

app.use(express.static(path.join(ROOT, 'public')));

fs.mkdirSync(path.dirname(DATA), {recursive: true});
app.listen(PORT, HOST, () => {
  console.log(`TaskFlow (Qwen-authored modules) on http://${HOST}:${PORT}`);
});
