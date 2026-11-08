// archagent/visual/harness.mjs — component test harness server.
//
// Session 034 TRUSTED-SCAFFOLD test infrastructure.  Serves ISOLATED
// component pages (fixed disclosure markup per curriculum task) plus the
// candidate CSS under test, so each staged CSS piece can be auto-verified
// against measurable acceptance criteria before it enters the application.
// The markup below is a TEST FIXTURE (like the check code in the module
// evaluators) — it is not application code.
//
// Routes:
//   GET /h/<task>   harness page for a curriculum task
//   GET /css        the candidate CSS (read fresh each request)
//   GET /health
//
// Usage: node archagent/visual/harness.mjs --css path/to/candidate.css \
//          [--port 4190]
'use strict';
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import path from 'node:path';

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : dflt;
}

const CSS_PATH = path.resolve(arg('css', '/tmp/harness-candidate.css'));
const PORT = Number(arg('port', 4190));

// Fixed test markup per curriculum task (disclosed fixtures).  Each fixture
// instantiates the component the task must style, with the exact class
// contract the application will use.
const FIXTURES = {
  'design-tokens': `<div class="t-token-grid">
  <span class="t-token t-bg-surface">surface</span>
  <span class="t-token t-text-strong">strong text</span>
  <span class="t-token t-text-muted">muted text</span>
</div>`,
  'base-reset': `<div class="stack">
  <p>Body paragraph one.</p>
  <p>Body paragraph two.</p>
  <span class="t-label">label</span>
</div>`,
  'typography-scale': `<article class="t-type">
  <h1>Primary heading</h1>
  <h2>Section heading</h2>
  <h3>Sub heading</h3>
  <p>Body copy that is long enough to wrap at narrow widths.</p>
  <span class="t-muted">Muted caption</span>
</article>`,
  'spacing-layout': `<div class="stack">
  <div class="row"><span class="card">A</span><span class="card">B</span></div>
  <div class="grid"><span class="card">1</span><span class="card">2</span><span class="card">3</span></div>
</div>`,
  'card': `<div class="stack">
  <article class="card"><h3>Card title</h3><p>Card body copy.</p></article>
  <article class="card card-interactive"><h3>Clickable</h3><p>Hover me.</p></article>
</div>`,
  'button-basics': `<div class="row">
  <button class="btn">Save</button>
  <button class="btn btn-primary">Create project</button>
  <button class="btn" disabled>Disabled</button>
</div>`,
  'button-variants': `<div class="row">
  <button class="btn btn-primary">Primary</button>
  <button class="btn btn-ghost">Ghost</button>
  <button class="btn btn-danger">Delete</button>
</div>`,
  'form-inputs': `<form class="stack">
  <label class="field"><span class="field-label">Title</span>
    <input class="input" placeholder="Task title"></label>
  <label class="field"><span class="field-label">Priority</span>
    <select class="select"><option>high</option><option>medium</option></select></label>
  <input class="input is-invalid" value="">
  <p class="field-error">Title is required</p>
</form>`,
  'interactive-states': `<div class="row">
  <button class="btn">Hover me</button>
  <a class="link" href="#">A link</a>
</div>`,
  'color-contrast': `<div class="t-bg-app">
  <p class="t-text-strong">Strong text</p>
  <p class="t-text-muted">Muted text</p>
  <span class="badge badge-neutral">neutral</span>
  <span class="badge badge-high">high</span>
  <span class="badge badge-medium">medium</span>
  <span class="badge badge-low">low</span>
</div>`,
  'breakpoints': `<div class="two-col">
  <div class="card">Column one</div>
  <div class="card">Column two</div>
</div>`,
  'app-header': `<header class="app-header">
  <div class="brand"><h1 class="brand-name">TaskFlow</h1>
    <span class="brand-tag">project workspace</span></div>
  <div class="header-actions"><span class="offline-badge">offline demo</span></div>
</header>`,
  'app-nav': `<nav class="app-nav">
  <h2 class="nav-title">Projects</h2>
  <form class="add-form"><input class="input" placeholder="New project">
    <button class="btn btn-primary" type="submit">Add</button></form>
  <div class="nav-list">
    <button class="project-btn"><span class="nav-item-name">Website Redesign</span></button>
    <button class="project-btn"><span class="nav-item-name">Mobile App v2</span></button>
    <button class="project-btn"><span class="nav-item-name">API Migration</span></button>
  </div>
</nav>`,
  'badge': `<div class="row">
  <span class="badge badge-high">high</span>
  <span class="badge badge-medium">medium</span>
  <span class="badge badge-low">low</span>
  <span class="badge badge-done">done</span>
  <span class="badge badge-todo">todo</span>
  <span class="badge badge-doing">doing</span>
</div>`,
  'progress': `<div class="progress-card">
  <div class="progress-head"><span class="progress-label">Progress</span>
    <span class="progress-text">50% (1/2)</span></div>
  <div class="progress"><div class="progress-fill"></div></div>
</div>`,
  'task-row': `<div class="task-list">
  <article class="task-row"><label class="task-check">
    <input type="checkbox"><span class="task-title">Draft homepage</span></label>
    <span class="badge badge-high">high</span>
    <span class="badge badge-done">done</span>
    <span class="task-actions"><button class="btn btn-ghost">edit</button>
      <button class="btn btn-danger">delete</button></span></article>
  <article class="task-row"><label class="task-check">
    <input type="checkbox"><span class="task-title">Review colors</span></label>
    <span class="badge badge-low">low</span>
    <span class="badge badge-todo">todo</span>
    <span class="task-actions"><button class="btn btn-ghost">edit</button>
      <button class="btn btn-danger">delete</button></span></article>
  <article class="task-row task-done"><label class="task-check">
    <input type="checkbox" checked><span class="task-title">Hero animation</span></label>
    <span class="badge badge-medium">medium</span>
    <span class="badge badge-doing">doing</span>
    <span class="task-actions"><button class="btn btn-ghost">edit</button>
      <button class="btn btn-danger">delete</button></span></article>
</div>`,
  'empty-state': `<div class="empty-state">
  <div class="empty-icon">0</div>
  <h3 class="empty-title">No tasks yet</h3>
  <p class="empty-text">Add your first task to get started.</p>
</div>`,
  'modal': `<div class="modal-overlay">
  <div class="modal" role="dialog">
    <h3 class="modal-title">Rename task</h3>
    <input class="input" value="Draft homepage">
    <div class="modal-actions"><button class="btn">Cancel</button>
      <button class="btn btn-primary">Save</button></div>
  </div>
</div>`,
  'toast': `<div class="toast-stack">
  <div class="toast toast-success">Task created</div>
  <div class="toast toast-error">Could not reach server</div>
</div>`,
  'skeleton': `<div class="stack">
  <div class="skeleton skeleton-line"></div>
  <div class="skeleton skeleton-line"></div>
  <div class="skeleton skeleton-block"></div>
</div>`,
  'app-shell': `<div class="app">
  <div class="app-side">
    <header class="app-header"><div class="brand">
      <h1 class="brand-name">TaskFlow</h1></div></header>
    <nav class="app-nav"><h2 class="nav-title">Projects</h2>
      <div class="nav-list">
        <button class="project-btn"><span class="nav-item-name">Website Redesign</span></button>
        <button class="project-btn"><span class="nav-item-name">Mobile App v2</span></button>
      </div></nav>
  </div>
  <main class="app-main">
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">Website Redesign</h2>
        <span class="progress">50% (1/2)</span></div>
      <div class="task-list">
        <article class="task-row"><span class="task-title">Draft homepage</span></article>
      </div>
    </section>
  </main>
</div>`,
};

const PAGE = (task, body) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>harness:${task}</title>
<link rel="stylesheet" href="/css">
</head><body class="harness-body" data-task="${task}">
${body}
</body></html>`;

createServer((req, res) => {
  if (req.url === '/health') { res.writeHead(200); return res.end('ok'); }
  if (req.url === '/css') {
    try {
      const css = readFileSync(CSS_PATH, 'utf8');
      res.writeHead(200, {'Content-Type': 'text/css; charset=utf-8'});
      return res.end(css);
    } catch (e) {
      res.writeHead(500); return res.end('css read error');
    }
  }
  const m = req.url.match(/^\/h\/([a-z0-9-]+)$/);
  if (m && FIXTURES[m[1]]) {
    res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
    return res.end(PAGE(m[1], FIXTURES[m[1]]));
  }
  res.writeHead(404); res.end('no such harness task');
}).listen(PORT, '127.0.0.1', () =>
  console.log(`harness on http://127.0.0.1:${PORT} css=${CSS_PATH}`));
