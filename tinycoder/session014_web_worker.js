// Trusted host-provided fixtures + generated JavaScript are evaluated ONLY inside
// a short-lived restricted Docker container. Never invoke this file on a host.
const fs = require('node:fs');
const vm = require('node:vm');
const esbuild = require('esbuild');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const express = require('express');
const supertest = require('supertest');

const [, , sourcePath, outputPath] = process.argv;
if (!fs.existsSync('/.dockerenv')) throw Error('Refusing to run outside Docker');
if (!sourcePath || !outputPath) throw Error('Expected source JSON and destination JSON');
const entries = JSON.parse(fs.readFileSync(sourcePath, 'utf8'));
if (!Array.isArray(entries) || entries.length < 1 || entries.length > 5) throw Error('Invalid evaluation batch');

function validateAndLoad(source, name) {
  // Append only an instrumentation export; never patch a generated function body.
  const wrapped = `${source}\n;module.exports = ${name};\n`;
  const compiled = esbuild.transformSync(wrapped, {
    loader: 'jsx', format: 'cjs', target: 'es2022', jsx: 'transform',
    jsxFactory: 'React.createElement', jsxFragment: 'React.Fragment'
  }).code;
  const exposed = { exports: {} };
  const allowRequire = (id) => {
    if (id === 'react') return React;
    if (id === 'express') return express;
    throw Error(`Module '${id}' not allowlisted`);
  };
  const ctx = vm.createContext({module: exposed, exports: exposed.exports, require: allowRequire,
                                console: {log() {}, warn() {}, error() {}}});
  new vm.Script(compiled, {filename: 'candidate.js'}).runInContext(ctx, {timeout: 1500});
  if (typeof exposed.exports !== 'function') throw Error('Expected named function export');
  return exposed.exports;
}

async function evaluateOne(entry) {
  const {task, solution} = entry;
  if (typeof solution !== 'string' || solution.length > 40000) throw Error('Solution too long');
  let parsed;
  try {
    parsed = validateAndLoad(solution, task.name);
  } catch (error) {
    // Distinguish transpile syntax rejection from JS runtime/entry failures.
    try {
      esbuild.transformSync(`${solution}\n;module.exports=${task.name};`, {
        loader: 'jsx', format: 'cjs', target: 'es2022',
        jsx: 'transform', jsxFactory: 'React.createElement'
      });
    } catch (parseFailure) {
      return {task_id: task.task_id, syntax_valid: false, passed: false,
              failure_bin: 'syntax_invalid', error: String(parseFailure).slice(0,400)};
    }
    return {task_id: task.task_id, syntax_valid: true, passed: false,
            failure_bin: 'unhandled_exception', error: String(error).slice(0,400)};
  }
  try {
    for (const t of task.tests) {
      if (task.mode === 'ui') {
        const element = React.createElement(parsed, t.props);
        const html = ReactDOMServer.renderToStaticMarkup(element);
        for (const fragment of t.contains || []) {
          if (!html.includes(fragment)) throw Error(`Missing expected markup: ${fragment}`);
        }
        for (const fragment of t.not_contains || []) {
          if (html.includes(fragment)) throw Error(`Unexpected markup: ${fragment}`);
        }
      } else if (task.mode === 'backend') {
        const app = await Promise.resolve(parsed());
        if (!app || typeof app.handle !== 'function') throw Error('Function did not return Express app');
        let request = supertest(app)[t.method](t.path).timeout({response: 2500, deadline: 4000});
        if (t.body !== null) request = request.send(t.body);
        const response = await request;
        if (response.status !== 200 || JSON.stringify(response.body) !== JSON.stringify(t.expected)) {
          throw Error(`Expected status 200 & ${JSON.stringify(t.expected)}; got ${response.status} & ${JSON.stringify(response.body)}`);
        }
      } else throw Error('Unknown benchmark mode');
    }
    return {task_id: task.task_id, syntax_valid: true, passed: true,
            failure_bin: 'passed', error: null};
  } catch (error) {
    const msg = String(error);
    const runtime = error instanceof TypeError || error instanceof ReferenceError ||
                    /timed out|not a function|did not return Express app/i.test(msg);
    return {task_id: task.task_id, syntax_valid: true, passed: false,
            failure_bin: runtime ? 'unhandled_exception' : 'assertion_error',
            error: msg.slice(0,400)};
  }
}

async function main() {
  const results = [];
  for (const task of entries) results.push(await evaluateOne(task));
  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2) + '\n');
}
main().catch(err => {console.error(err);process.exitCode=1});
