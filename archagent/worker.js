// archagent/worker.js — isolated evaluator for TaskFlow modules.
// Every Qwen-produced byte runs inside a Node vm realm with a module
// allowlist, codeGeneration disabled and hard timeouts, or inside a
// `python3 -I -B` subprocess for the Python module.  Docker is unavailable
// in the recycled sandbox, so this is the disclosed SESSION-LOCAL-EVAL
// mode (same discipline as Session031/032: vm realms, allowlists,
// timeouts, byte-identical checks; the production CI workflow runs the
// same logic inside Docker).
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const os = require('node:os');
const {spawnSync} = require('node:child_process');
const http = require('node:http');
const esbuild = require('esbuild');
const express = require('express');
const request = require('supertest');
const React = require('react');
const {createRoot} = require('react-dom/client');
const {JSDOM} = require('jsdom');

if (!fs.existsSync('/.dockerenv') && process.env.ARCHAGENT_LOCAL_EVAL !== '1')
  throw Error('Isolated evaluator (ARCHAGENT_LOCAL_EVAL=1 is the disclosed local mode)');

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const {role, source, cases, phase, extra} = input;
const out = {
  role, phase, passed: false, syntax_valid: false,
  checks: {}, failures: [], error: null, usage: {},
};
const PY_WORKER = process.env.ARCHAGENT_PY_WORKER ||
  path.join(__dirname, 'py_worker.py');

function fail(reason) { out.error = String(reason).slice(0, 400); }
function check(name, ok, detail) {
  out.checks[name] = !!ok;
  if (!ok) out.failures.push({check: name, detail: String(detail || '').slice(0, 300)});
}

// ---------------------------------------------------------------------------
// realm loader (shared by store/api/ui)
// ---------------------------------------------------------------------------
function loadModule(source, name, role, allowFs) {
  const compiled = esbuild.transformSync(
    source + `\nmodule.exports = ${name};`,
    {loader: role === 'ui' ? 'jsx' : 'js', format: 'cjs', target: 'es2022'}).code;
  const module = {exports: {}};
  const context = vm.createContext({
    module, exports: module.exports, React, console: {log(){}, warn(){}, error(){}},
    setTimeout: (fn, ms) => setTimeout(fn, Math.min(Number(ms) || 0, 800)),
    clearTimeout,
    require(id) {
      if (id === 'react') return React;
      if (id === 'express') return express;
      if (allowFs && (id === 'node:fs' || id === 'fs')) return fs;
      throw Error('Disallowed module ' + id);
    },
  }, {codeGeneration: {strings: false, wasm: false}});
  new vm.Script(compiled, {filename: 'qwen-' + role + '.js'})
    .runInContext(context, {timeout: 2500});
  return module.exports;
}

function errLine(error) {
  const m = /qwen-[a-z]+\.js:(\d+):(\d+)/.exec(String(error && error.stack || error));
  return m ? {line: Number(m[1]), col: Number(m[2])} : null;
}

// trusted scaffold processor (reference semantics of the Python contract);
// used when no logic module is supplied.  Disclosed TRUSTED-SCAFFOLD.
function trustedProcessor(p) {
  const tasks = p.tasks || [];
  const total = tasks.length;
  const done = tasks.filter(t => t.status === 'done').length;
  const by_priority = {low: 0, medium: 0, high: 0};
  const by_status = {todo: 0, doing: 0, done: 0};
  for (const t of tasks) {
    if (by_priority[t.priority] !== undefined) by_priority[t.priority]++;
    if (by_status[t.status] !== undefined) by_status[t.status]++;
  }
  return {total, done, remaining: total - done,
          percent: total ? Math.round(100 * done / total) : 0,
          by_priority, by_status};
}

function bridgedProcessor(logicSource) {
  // Run the model's Python logic module in an isolated subprocess per call.
  return (payload) => {
    const p = spawnSync('python3', ['-I', '-B', PY_WORKER], {
      input: JSON.stringify({source: logicSource, payload, fn: 'summarize_project'}),
      encoding: 'utf8', timeout: 4000, maxBuffer: 65536,
      env: {PYTHONDONTWRITEBYTECODE: '1', PYTHONHASHSEED: '0'},
    });
    if (p.error || p.status !== 0)
      throw Error('processor bridge failed: ' + (p.error ? p.error.message : String(p.stderr).slice(-160)));
    const r = JSON.parse(p.stdout);
    if (!r.ok) throw Error('processor raised: ' + r.error);
    return r.value;
  };
}

// ---------------------------------------------------------------------------
// role evaluators
// ---------------------------------------------------------------------------
function evalLogic() {
  const p = spawnSync('python3', ['-I', '-B', PY_WORKER], {
    input: JSON.stringify({source, cases, fn: 'summarize_project'}),
    encoding: 'utf8', timeout: 8000, maxBuffer: 65536,
    env: {PYTHONDONTWRITEBYTECODE: '1', PYTHONHASHSEED: '0'},
  });
  if (p.error) return fail('python worker: ' + p.error.message);
  if (p.status !== 0) return fail('python worker crashed: ' + String(p.stderr).slice(-300));
  const r = JSON.parse(p.stdout);
  out.syntax_valid = !!r.syntax_valid;
  if (!r.syntax_valid) return fail('syntax: ' + r.error);
  if (!r.ok) return fail('runtime: ' + r.error);
  for (let i = 0; i < r.results.length; i++) {
    check('case' + i, r.results[i].ok,
      'expected ' + JSON.stringify(r.results[i].expected) + ' got ' +
      JSON.stringify(r.results[i].got));
  }
}

function evalStore() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'taskflow-store-'));
  const file = path.join(tmp, 'db.json');
  let store, factory;
  try {
    factory = loadModule(source, 'createStore', 'store', true);
    if (typeof factory !== 'function') return fail('createStore is not a function');
    store = factory(file);
  } catch (e) { return fail('load: ' + e.message + (errLine(e) ? ' @' + JSON.stringify(errLine(e)) : '')); }
  out.syntax_valid = true;
  const fresh = () => { try { return factory(file); } catch (e) { return null; } };
  for (const step of cases) {
    const name = step.op + (step.id ? ':' + step.id : '')
      + (step.body ? ':' + JSON.stringify(step.body).slice(0, 40) : '')
      + (step.filter ? ':' + JSON.stringify(step.filter).slice(0, 40) : '');
    try {
      if (step.op === 'reload') { store = fresh(); check(name, !!store, 'reload returned non-object'); continue; }
      if (step.op === 'persistedShape') {
        let raw;
        try { raw = JSON.parse(fs.readFileSync(file, 'utf8')); }
        catch (e) { check(name, false, 'cannot read/parse ' + path.basename(file) + ': ' + e.message); continue; }
        const okShape = raw && Array.isArray(raw.projects) && Array.isArray(raw.tasks);
        check(name, okShape, 'file shape ' + JSON.stringify(Object.keys(raw || {})));
        continue;
      }
      let result, threw = false;
      try {
        if (step.op === 'listProjects') result = store.listProjects();
        else if (step.op === 'createProject') result = store.createProject(step.body);
        else if (step.op === 'updateProject') result = store.updateProject(step.id, step.body);
        else if (step.op === 'deleteProject') result = store.deleteProject(step.id);
        else if (step.op === 'listTasks') result = store.listTasks(step.filter || {});
        else if (step.op === 'createTask') result = store.createTask(step.body);
        else if (step.op === 'updateTask') result = store.updateTask(step.id, step.body);
        else if (step.op === 'deleteTask') result = store.deleteTask(step.id);
        else { check(name, false, 'unknown op ' + step.op); continue; }
      } catch (e) { threw = true; result = e; }
      if (step.expectError) {
        check(name, threw, threw ? '' : 'expected Error, returned ' + JSON.stringify(result).slice(0, 120));
      } else if (threw) {
        const at = errLine(result);
        check(name, false, 'threw ' + result.message + (at ? ' @line ' + at.line : ''));
      } else if ('expect' in step) {
        const ok = typeof step.expect === 'object' && step.expect !== null && !Array.isArray(step.expect)
          ? Object.entries(step.expect).every(([k, v]) =>
              JSON.stringify(result && result[k]) === JSON.stringify(v))
          : JSON.stringify(result) === JSON.stringify(step.expect);
        check(name, ok, 'expected ' + JSON.stringify(step.expect).slice(0, 140) + ' got ' + JSON.stringify(result).slice(0, 140));
      } else if ('expectCount' in step) {
        const n = Array.isArray(result) ? result.length : -1;
        check(name, n === step.expectCount, 'expected ' + step.expectCount + ' items, got ' + n);
      } else {
        check(name, true);
      }
    } catch (outer) { check(name, false, 'harness: ' + outer.message); }
  }
  try { fs.rmSync(tmp, {recursive: true, force: true}); } catch {}
}

async function evalApi() {
  let createApi;
  try {
    createApi = loadModule(source, 'createApi', 'api', false);
    if (typeof createApi !== 'function') return fail('createApi is not a function');
  } catch (e) { return fail('load: ' + e.message + (errLine(e) ? ' @' + JSON.stringify(errLine(e)) : '')); }
  out.syntax_valid = true;
  const processor = extra && extra.logicSource ? bridgedProcessor(extra.logicSource) : trustedProcessor;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'taskflow-api-'));
  const file = path.join(tmp, 'db.json');
  const app = express();
  try {
    const factory = loadModule(extra.storeSource, 'createStore', 'store', true);
    createApi(app, factory(file), processor);
  } catch (e) { return fail('setup: ' + e.message); }
  const server = await new Promise(resolve => {
    const s = app.listen(0, '127.0.0.1', () => resolve(s));
  });
  const port = server.address().port;

  function call(method, urlPath, body) {
    return new Promise(resolve => {
      const opts = {method: method.toUpperCase(), host: '127.0.0.1', port,
                    path: urlPath, headers: {'accept': 'application/json'}};
      if (body !== undefined) {
        const payload = JSON.stringify(body);
        opts.headers['content-type'] = 'application/json';
        opts.headers['content-length'] = Buffer.byteLength(payload);
      }
      const req = http.request(opts, res => {
        let d = '';
        res.on('data', c => { d += c; });
        res.on('end', () => resolve({status: res.statusCode, body: d.slice(0, 8000)}));
      });
      req.setTimeout(2500, () => { req.destroy(); resolve({status: -1, body: ''}); });
      req.on('error', () => resolve({status: -1, body: ''}));
      if (body !== undefined) req.write(JSON.stringify(body));
      req.end();
    });
  }

  for (const c of cases) {
    const res = await call(c.method, c.path, c.body);
    let ok = res.status === c.expect_status;
    let detail = 'status ' + res.status + ' (want ' + c.expect_status + ')';
    if (ok && c.expect_body) {
      try { ok = JSON.stringify(JSON.parse(res.body)) === JSON.stringify(c.expect_body); }
      catch { ok = false; }
      if (!ok) detail += ' body ' + String(res.body).slice(0, 140);
    }
    if (ok && c.expect_body_contains) {
      let parsed = null;
      try { parsed = JSON.parse(res.body); } catch {}
      for (const [k, v] of Object.entries(c.expect_body_contains)) {
        if (v === null) { ok = ok && parsed && parsed[k] !== undefined; }
        else if (typeof v === 'object') {
          for (const [k2, v2] of Object.entries(v)) {
            ok = ok && parsed && parsed[k] && JSON.stringify(parsed[k][k2]) === JSON.stringify(v2);
            if (!ok) { detail += ` ${k}.${k2}=${JSON.stringify(parsed && parsed[k] && parsed[k][k2])} want ${JSON.stringify(v2)}`; break; }
          }
        } else {
          ok = ok && parsed && JSON.stringify(parsed[k]) === JSON.stringify(v);
          if (!ok) detail += ` ${k}=${JSON.stringify(parsed && parsed[k])} want ${JSON.stringify(v)}`;
        }
        if (!ok) break;
      }
    }
    if (ok && c.expect_count) {
      const [key, n] = c.expect_count;
      let parsed = null;
      try { parsed = JSON.parse(res.body); } catch {}
      const got = parsed && Array.isArray(parsed[key]) ? parsed[key].length : -1;
      ok = got === n;
      if (!ok) detail += ` ${key}.length=${got} want ${n}`;
    }
    check(c.name, ok, detail);
  }
  await new Promise(r => server.close(r));
  try { fs.rmSync(tmp, {recursive: true, force: true}); } catch {}
}

async function evalUi() {
  let App;
  try {
    App = loadModule(source, 'App', 'ui', false);
    if (typeof App !== 'function') return fail('App is not a function');
  } catch (e) { return fail('load: ' + e.message + (errLine(e) ? ' @' + JSON.stringify(errLine(e)) : '')); }
  out.syntax_valid = true;

  // Behavioral mount: fetch always fails -> REQUIRED offline demo mode.
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',
    {url: 'https://taskflow.test/', pretendToBeVisual: true});
  const w = dom.window;
  const realSetTimeout = setTimeout.bind(global);
  const raf = (cb) => realSetTimeout(cb, 16);
  const patches = {
    document: w.document, window: w, navigator: w.navigator,
    fetch: () => Promise.reject(new Error('offline')),
    setTimeout: (...a) => realSetTimeout(...a),
    clearTimeout,
    requestAnimationFrame: raf, cancelAnimationFrame: () => {},
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const saved = {};
  for (const k of Object.keys(patches)) {
    saved[k] = global[k];
    try { Object.defineProperty(global, k, {value: patches[k], configurable: true, writable: true}); }
    catch { global[k] = patches[k]; }
  }
  let html = '';
  try {
    const root = createRoot(w.document.getElementById('root'));
    root.render(React.createElement(App));
    const t0 = Date.now();
    while (Date.now() - t0 < 4000) {
      await wait(60);
      const markup = w.document.body.innerHTML;
      if (markup.includes('offline-badge') && markup.includes('task-row')) break;
    }
    html = w.document.body.innerHTML;
  } catch (e) {
    fail('mount: ' + e.message);
  } finally {
    for (const k of Object.keys(saved)) {
      try {
        if (saved[k] === undefined) delete global[k];
        else Object.defineProperty(global, k, {value: saved[k], configurable: true, writable: true});
      } catch { global[k] = saved[k]; }
    }
  }
  if (out.error) return;
  const checks = {
    offline_badge: [() => w.document.querySelector('.offline-badge') &&
                         /offline/i.test(w.document.querySelector('.offline-badge').textContent), 'no .offline-badge with the word offline'],
    demo_project: [() => html.includes('Website Redesign'), 'demo project name not rendered'],
    progress: [() => { const el = w.document.querySelector('.progress'); return el && /50% \(1\/2\)/.test(el.textContent); }, '.progress must show "50% (1/2)"'],
    task_rows: [() => w.document.querySelectorAll('.task-row').length >= 2, 'need >= 2 .task-row'],
    task_titles: [() => html.includes('Draft homepage') && html.includes('Review colors'), 'demo task titles not rendered'],
    priority_text: [() => /high/.test(html) && /low/.test(html), 'priority text not rendered'],
    filters: [() => ['.filter-all', '.filter-todo', '.filter-doing', '.filter-done'].every(s => w.document.querySelector(s)), 'missing filter buttons'],
    search: [() => !!w.document.querySelector('.search'), 'missing .search input'],
    add_form: [() => !!w.document.querySelector('.add-form'), 'missing .add-form'],
    toggle: [() => !!w.document.querySelector('.toggle'), 'missing .toggle button'],
    edit: [() => !!w.document.querySelector('.edit'), 'missing .edit button'],
    delete_btn: [() => !!w.document.querySelector('.delete'), 'missing .delete button'],
    project_btn: [() => !!w.document.querySelector('.project-btn'), 'missing .project-btn'],
  };
  for (const [name, [fn, why]] of Object.entries(checks)) {
    let ok = false;
    try { ok = !!fn(); } catch {}
    check(name, ok, why);
  }
  out.ui_markup = html.slice(0, 4000);
}

function evalCss() {
  let css;
  try {
    const module = {exports: {}};
    const context = vm.createContext({
      module, exports: module.exports, console: {log(){}, warn(){}, error(){}},
    }, {codeGeneration: {strings: false, wasm: false}});
    const compiled = esbuild.transformSync(source, {loader: 'js', format: 'cjs', target: 'es2022'}).code;
    new vm.Script(compiled, {filename: 'qwen-css.js'}).runInContext(context, {timeout: 1500});
    css = module.exports;
    out.syntax_valid = true;
  } catch (e) { return fail('load: ' + e.message); }
  if (typeof css !== 'string') return fail('module.exports is not a string');
  const required = ['.app', '.sidebar', '.project-btn', '.task-row', '.priority-high',
    '.priority-medium', '.priority-low', '.progress', '.progress-fill', '.filter-all',
    '.filter-todo', '.filter-doing', '.filter-done', '.search', '.offline-badge', '.add-form'];
  for (const sel of required) check('has' + sel.slice(1), css.includes(sel), sel + ' missing');
  check('media', /@media\s*\(max-width:\s*720px\)/.test(css), 'no @media (max-width: 720px)');
  check('media_count', (css.match(/@media/g) || []).length === 1, 'exactly one @media block');
  const appRule = /\.app\s*\{[^}]*\}/.exec(css);
  check('app_flex', !!appRule && /display\s*:\s*flex/.test(appRule[0]), '.app must use display:flex');
  const progRule = /\.progress\s*\{[^}]*\}/.exec(css);
  check('progress_bg', !!progRule && /background/.test(progRule[0]), '.progress must set a background');
  check('no_external', !/url\(|@import|http/.test(css), 'no external urls/imports');
  check('no_comments', !/\/\*/.test(css), 'no CSS comments');
}

(async () => {
  try {
    if (role === 'logic') evalLogic();
    else if (role === 'store') evalStore();
    else if (role === 'api') await evalApi();
    else if (role === 'ui') await evalUi();
    else if (role === 'css') evalCss();
    else fail('unknown role ' + role);
  } catch (e) { fail('worker: ' + (e && e.stack || e)); }
  out.passed = !out.error && Object.keys(out.checks).length > 0 &&
    Object.values(out.checks).every(Boolean);
  fs.writeFileSync(process.argv[3], JSON.stringify(out));
  process.exit(0);
})();
