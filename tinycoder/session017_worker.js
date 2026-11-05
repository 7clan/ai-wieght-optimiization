// Trusted full-stack contract evaluator. NEVER execute this outside Docker.
// One app per container: runaway JS/Python receives a hard outer timeout.
const fs = require('node:fs');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const esbuild = require('esbuild');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const express = require('express');
const supertest = require('supertest');

if (!fs.existsSync('/.dockerenv')) throw Error('Docker required');
if (process.argv.length !== 4) throw Error('Expected input and output paths');
const request = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const { task, modules, cases } = request;
if (!task || !Array.isArray(cases) || cases.length > 8 || cases.length === 0 ||
    !modules || ['logic', 'api', 'ui'].some(k => typeof modules[k] !== 'string')) {
  throw Error('Malformed app evaluation request');
}

function loadJs(source, exportName) {
  if (source.length > 30000) throw Error('JS module too long');
  // Syntax errors and import violations are classified separately below.
  const compiled = esbuild.transformSync(`${source}\nmodule.exports=${exportName};`, {
    loader: 'jsx', format: 'cjs', target: 'es2022', jsx: 'transform',
    jsxFactory: 'React.createElement', jsxFragment: 'React.Fragment'
  }).code;
  const exposed = { exports: {} };
  const allowRequire = id => {
    if (id === 'react') return React;
    if (id === 'express') return express;
    throw Error(`Disallowed module: ${id}`);
  };
  const context = vm.createContext({ module: exposed, exports: exposed.exports,
    require: allowRequire, console: {log(){}, error(){}, warn(){}} });
  new vm.Script(compiled, {filename: 'generated.js'}).runInContext(context, {timeout: 1300});
  if (typeof exposed.exports !== 'function') throw Error(`Expected function ${exportName}`);
  return exposed.exports;
}

function python(source, payload) {
  const run = spawnSync('python3', ['-I', '-B', '/opt/fullstack/py_worker.py'], {
    input: JSON.stringify({source, payload}), encoding: 'utf8', timeout: 1700,
    maxBuffer: 32768, env: {PYTHONDONTWRITEBYTECODE:'1', PYTHONHASHSEED:'0'}
  });
  if (run.error) return {syntax_valid: true, ok:false, error:String(run.error)};
  if (run.status !== 0) return {syntax_valid:true, ok:false,
    error:`Python exit ${run.status}: ${run.stderr.slice(0,160)}`};
  try {return JSON.parse(run.stdout);} catch(error) {return {syntax_valid:true,ok:false,error:'Invalid Python result'};}
}

function compare(actual, expected) {
  // Stable recursive comparison; inputs/outputs are simple JSON scalars/arrays.
  const stable = v => JSON.stringify(v, (_, x) => x && typeof x === 'object' &&
    !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort()) : x);
  return stable(actual) === stable(expected);
}

function display(value) {
  if (value === null) return 'none';
  if (Array.isArray(value)) return value.map(String).join(', ');
  return String(value);
}

async function evaluate() {
  const result = {task_id:task.task_id, syntax_valid:true, passed:false,
    modules: {logic:{syntax_valid:true,passed:false},
              api:{syntax_valid:true,passed:false},
              ui:{syntax_valid:true,passed:false}},
    integration:{passed:false,error:'Module checks incomplete'},
    failure_bin:'unclassified_logic_gap'};
  let appFactory, view;
  for (const [name,fn] of [['api','createApp'],['ui','ResultView']]) {
    try {
      if (name === 'api') appFactory = loadJs(modules[name],fn);
      else {
        view = loadJs(modules[name],fn);
        // Also verify that JSX and imports can be bundled for the client.
        esbuild.buildSync({stdin:{contents:modules[name],loader:'jsx',
          resolveDir:'/opt/fullstack',sourcefile:'ResultView.jsx'},bundle:true,
          platform:'browser',write:false,logLevel:'silent'});
      }
      result.modules[name].syntax_valid = true;
    } catch(error) {
      // Determine syntax by parsing alone, not by interpreting failure text.
      try {esbuild.transformSync(modules[name],{loader:'jsx'});
        result.modules[name].syntax_valid=true;}
      catch(_) {result.modules[name].syntax_valid=false;}
      result.modules[name].error=String(error).slice(0,240);
    }
  }

  // Python tests are executed in a separate bounded child INSIDE Docker.
  let logicOk=true;
  for (const test of cases) {
    const check=python(modules.logic,test.payload);
    if (!check.syntax_valid) result.modules.logic.syntax_valid=false;
    if (!check.ok || !compare(check.value,test.expected)) {
      logicOk=false;
      result.modules.logic.error=check.error ||
        `Python expected ${JSON.stringify(test.expected)} but got ${JSON.stringify(check.value)}`;
      break;
    }
  }
  result.modules.logic.passed=logicOk;

  if (appFactory) {
    try {
      const app=await Promise.resolve(appFactory(x=>x));
      if (!app || typeof app.handle !== 'function') throw Error('createApp did not return an Express app');
      for (const test of cases) {
        // Stub keeps this module test independent of generated Python.
        const stubApp=await Promise.resolve(appFactory(()=>test.expected));
        const response=await supertest(stubApp).post(task.contract.route)
          .send(test.payload).timeout({response:1700,deadline:2200});
        if (response.status !== 200 || !compare(response.body,{data:test.expected})) {
          throw Error(`API expected ${JSON.stringify({data:test.expected})}; got HTTP ${response.status} ${JSON.stringify(response.body)}`);
        }
      }
      result.modules.api.passed=true;
    } catch(error) {result.modules.api.error=String(error).slice(0,240);}
  }
  if (view) {
    try {
      for (const test of cases) {
        const html=ReactDOMServer.renderToStaticMarkup(
          React.createElement(view,{data:test.expected}));
        const heading=`<h3>${task.contract.heading}</h3>`;
        const marker=`data-testid="${task.contract.ui_testid}"`;
        const value=display(test.expected.value);
        if (!html.includes('<section') || !html.includes(marker) ||
            !html.includes(heading) || !html.includes(`<output>${value}</output>`)) {
          throw Error(`UI missing markup ${heading}, ${marker} or output '${value}'; got ${html.slice(0,180)}`);
        }
      }
      result.modules.ui.passed=true;
    } catch(error) {result.modules.ui.error=String(error).slice(0,240);}
  }

  if (Object.values(result.modules).every(m=>m.passed)) {
    try {
      const integrated=await Promise.resolve(appFactory(input=>{
        const p=python(modules.logic,input);
        if (!p.ok) throw Error(p.error);
        return p.value;
      }));
      for (const test of cases) {
        const response=await supertest(integrated).post(task.contract.route)
          .send(test.payload).timeout({response:1700,deadline:2200});
        if (response.status!==200 || !compare(response.body,{data:test.expected}))
          throw Error(`End-to-end API mismatch HTTP ${response.status}: ${JSON.stringify(response.body)}`);
        const html=ReactDOMServer.renderToStaticMarkup(
          React.createElement(view,{data:response.body.data}));
        if (!html.includes(`<output>${display(test.expected.value)}</output>`))
          throw Error(`End-to-end React mismatch: ${html.slice(0,180)}`);
      }
      result.integration={passed:true,error:null};
      result.passed=true;
      result.failure_bin='passed';
    } catch(error) {result.integration={passed:false,error:String(error).slice(0,240)};}
  }
  result.syntax_valid=Object.values(result.modules).every(m=>m.syntax_valid);
  if (!result.passed) {
    if (!result.syntax_valid) result.failure_bin='syntax_invalid';
    else if (Object.values(result.modules).some(m=>m.error && /TypeError|ReferenceError|exit|timed out/i.test(m.error)))
      result.failure_bin='unhandled_exception';
    else result.failure_bin='assertion_error';
  }
  return result;
}

evaluate().then(result => {
  fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2)+'\n');
}).catch(err=>{console.error(err);process.exitCode=1;});
