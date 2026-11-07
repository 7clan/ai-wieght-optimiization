"""Staged UI builder: generate the TaskFlow React App in three pieces
(state+demo, handlers, JSX) — same architecture as the proven store/api
builders.

Every piece is 100% model bytes; anchors and assembly are disclosed
TRUSTED-SCAFFOLD.  Acceptance = the full offline-demo jsdom evaluation
passing every UI check (the evaluator mounts the app with failing fetch
and asserts the required offline mode, demo data, progress text and all
interactive elements render).
"""
from __future__ import annotations

import json
import os
import re as _re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from archagent import contracts, retrieval  # noqa: E402
from archagent.runner import (evaluate_module, score_of, sha,  # noqa: E402
                              _degenerate)

UI_HEADER = "const React = require('react');\nfunction App() {\n"
UI_FOOTER = "}\nmodule.exports = App;\n"

# The state anchor includes the exact contract demo dataset (public
# spec data, disclosed TRUSTED-SCAFFOLD — same class as signature
# anchors; the model writes all hooks, effects and handlers).
PIECE_ANCHORS = {
    "state": ("const React = require('react');\nfunction App() {\n"
              "  const DEMO_PROJECTS = [{ id: 'p1', name: 'Website"
              " Redesign', createdAt: '2026-11-07' }];\n"
              "  const DEMO_TASKS = [{ id: 't1', projectId: 'p1',"
              " title: 'Draft homepage', priority: 'high', status: 'done',"
              " createdAt: '2026-11-07' }, { id: 't2', projectId: 'p1',"
              " title: 'Review colors', priority: 'low', status: 'todo',"
              " createdAt: '2026-11-07' }];\n"),
    "api": "  async function api(url, opts) {\n",
    "handlers": "  async function api(url, opts) {\n",
    "addProject": "  async function addProject(e) {\n",
    "addTask": "  async function addTask(e) {\n",
    "toggle": "  async function toggle(t) {\n",
    "editTask": "  async function editTask(t) {\n",
    "removeTask": "  async function removeTask(t) {\n",
    "computed": "  const shown = offline ? DEMO_TASKS : tasks;\n",
    "jsx": "  return (\n",
}

HANDLER_PIECES = ["api", "addProject", "addTask", "toggle", "editTask",
                  "removeTask", "computed"]

HANDLER_SPECS = {
    "api": """Write the api(url, opts) helper for the TaskFlow App.
Write EXACTLY:
    const res = await fetch(url, opts);
    if (!res.ok) throw Error('request failed');
    return res.json();
  }
(the closing brace closes api). Nothing else.""",
    "addProject": """Write the addProject(e) submit handler. Write
EXACTLY:
    e.preventDefault();
    if (!form.project) return;
    if (offline) return;
    try {
      await api('/api/projects', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.project }) });
      const data = await api('/api/projects');
      setProjects(data.projects || []);
      setForm({ ...form, project: '' });
    } catch (e2) { setOffline(true); }
  }""",
    "addTask": """Write the addTask(e) submit handler. Write EXACTLY:
    e.preventDefault();
    if (!form.title) return;
    if (offline) {
      setTasks([...tasks, { id: 'd' + (tasks.length + 1),
        projectId: selectedId, title: form.title,
        priority: form.priority, status: 'todo',
        createdAt: '2026-11-07' }]);
      setForm({ ...form, title: '' });
      return;
    }
    try {
      await api('/api/tasks', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: selectedId,
          title: form.title, priority: form.priority }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
      setForm({ ...form, title: '' });
    } catch (e2) { setOffline(true); }
  }""",
    "toggle": """Write the toggle(t) handler. Write EXACTLY:
    const next = t.status === 'done' ? 'todo' : 'done';
    if (offline) {
      setTasks(tasks.map(x => x.id === t.id ? { ...x, status: next } : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }""",
    "editTask": """Write the editTask(t) handler. Write EXACTLY:
    const title = prompt('New title');
    if (!title) return;
    if (offline) {
      setTasks(tasks.map(x => x.id === t.id ? { ...x, title } : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }""",
    "removeTask": """Write the removeTask(t) handler. Write EXACTLY:
    if (offline) {
      setTasks(tasks.filter(x => x.id !== t.id));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'DELETE' });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }""",
    "computed": """Write the three computed values used by the JSX. Write
EXACTLY (continuing after the line that is already written):
  const doneCount = shown.filter(t => t.status === 'done').length;
  const pct = shown.length ? Math.round(100 * doneCount / shown.length) : 0;
Nothing else. (The first line — const shown = offline ? DEMO_TASKS :
tasks; — is already written as the anchor.)""",
}

STATE_SPEC = """Write the STATE SETUP for the TaskFlow App component (the
first lines inside function App()). Write EXACTLY these things:
1. five useState hooks, nothing else:
  const [projects, setProjects] = React.useState([]);
  const [selectedId, setSelectedId] = React.useState(null);
  const [tasks, setTasks] = React.useState([]);
  const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
  const [offline, setOffline] = React.useState(false);
2. exactly two useEffect hooks (DEMO_PROJECTS and DEMO_TASKS already
exist above, defined before your code):
  React.useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/projects');
        if (!res.ok) throw Error('bad');
        const data = await res.json();
        setProjects(data.projects || []);
      } catch (e) { setOffline(true); }
    })();
  }, []);
  React.useEffect(() => { }, [selectedId, offline]);
FORBIDDEN: no other hooks, no return statement, no JSX."""

HANDLERS_SPEC = """Write the HANDLERS for the TaskFlow App (inside App(),
after the state setup which already exists). Shared state: projects,
selectedId, tasks, form, offline (with setProjects, setSelectedId,
setTasks, setForm, setOffline) and the demo constants DEMO_PROJECTS,
DEMO_TASKS. Write EXACTLY this order:
1. an api helper that switches to offline mode when a request fails:
  async function api(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw Error('request failed');
    return res.json();
  }
2. addProject(e) — form submit: e.preventDefault(); if (!form.project) return;
   if offline, do nothing; else try { await api('/api/projects',
   { method: 'POST', headers: { 'Content-Type': 'application/json' },
   body: JSON.stringify({ name: form.project }) }); then
   setProjects((await api('/api/projects')).projects || []);
   setForm({ ...form, project: '' }); } catch (e) { setOffline(true); }
3. addTask(e) — like addProject but POSTs { projectId: selectedId,
   title: form.title, priority: form.priority } to /api/tasks, then
   refreshes tasks with GET /api/tasks?projectId= + selectedId and
   setTasks(data.tasks || []); when offline instead appends to tasks
   locally: setTasks([...tasks, { id: 'd' + (tasks.length + 1),
   projectId: selectedId, title: form.title, priority: form.priority,
   status: 'todo', createdAt: '2026-11-07' }]) and clears form.title.
4. toggle(t) — when offline: setTasks(tasks.map(x => x.id === t.id ?
   { ...x, status: x.status === 'done' ? 'todo' : 'done' } : x));
   otherwise PUT /api/tasks/ + t.id { status: next } then refetch the
   task list (same GET as addTask).
5. editTask(t) — const title = prompt('New title'); if (!title) return;
   offline: setTasks(tasks.map(x => x.id === t.id ? { ...x, title } : x));
   otherwise PUT { title } then refetch.
6. removeTask(t) — offline: setTasks(tasks.filter(x => x.id !== t.id));
   otherwise DELETE /api/tasks/ + t.id then refetch.
Every online path wraps its awaits in try/catch and calls
setOffline(true) in the catch. Finally, after all handlers, write these
three computed values (used by the JSX that follows):
  const shown = offline ? DEMO_TASKS : tasks;
  const doneCount = shown.filter(t => t.status === 'done').length;
  const pct = shown.length ? Math.round(100 * doneCount / shown.length) : 0;
No JSX, no return statement."""

JSX_SPEC = """Write the JSX RETURN for the TaskFlow App (inside App(),
after the state and handlers which already exist). The variables
available: projects, selectedId, tasks, form, offline (state), DEMO_PROJECTS,
DEMO_TASKS, addProject, addTask, toggle, editTask, removeTask (handlers).
Write EXACTLY one return statement:
  return (
    <div className="app">
      <aside className="sidebar">
        {offline && <div className="offline-badge">offline</div>}
        {(offline ? DEMO_PROJECTS : projects).map(p => (
          <button key={p.id} className="project-btn"
            onClick={() => setSelectedId(p.id)}>{p.name}</button>
        ))}
        <form className="add-form" onSubmit={addProject}>
          <input value={form.project}
            onChange={e => setForm({ ...form, project: e.target.value })}
            placeholder="New project" />
          <button type="submit">Add project</button>
        </form>
      </aside>
      <main>
        <div className="progress">{pct}% ({doneCount}/{shown.length})</div>
        <form className="add-form" onSubmit={addTask}>
          <input value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="New task" />
          <select value={form.priority}
            onChange={e => setForm({ ...form, priority: e.target.value })}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
          <button type="submit">Add task</button>
        </form>
        <div>
          <button className="filter-all">All</button>
          <button className="filter-todo">Todo</button>
          <button className="filter-doing">Doing</button>
          <button className="filter-done">Done</button>
          <input className="search" placeholder="Search" />
        </div>
        {shown.map(t => (
          <div key={t.id} className="task-row">
            <span>{t.title}</span>
            <span className={'priority-' + t.priority}>{t.priority}</span>
            <button className="toggle" onClick={() => toggle(t)}>
              {t.status === 'done' ? 'undo' : 'done'}</button>
            <button className="edit" onClick={() => editTask(t)}>edit</button>
            <button className="delete" onClick={() => removeTask(t)}>delete</button>
          </div>
        ))}
      </main>
    </div>
  );
The values shown, doneCount and pct already exist (computed at the end of
the handlers). Use them directly."""

EXAMPLES = contracts.EXAMPLES["ui"]


def _comment(text: str, width: int = 104) -> str:
    out = []
    for raw in text.splitlines():
        line = raw.rstrip()
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            if cut <= 0:
                cut = width
            out.append("// " + line[:cut])
            line = line[cut:].lstrip()
        out.append("// " + line if line else "//")
    return "\n".join(out) + "\n"


def piece_prompt(name: str, accepted_before: str, docs: bool) -> str:
    spec = {"state": STATE_SPEC, "handlers": HANDLERS_SPEC,
            "jsx": JSX_SPEC, **HANDLER_SPECS}[name]
    parts = [_comment(f"NEW TaskFlow UI piece: {name}. Complete the code "
                      "after the final brace/paren. No prose.")]
    parts.append(_comment(spec))
    parts.append(_comment(EXAMPLES))
    if docs:
        parts.append(retrieval.doc_block("ui"))
    if accepted_before:
        parts.append(_comment("Your own accepted App code so far:"))
        parts.append(_comment(accepted_before[:2600]))
    return "".join(parts) + "\n" + PIECE_ANCHORS[name]


def _extract_jsx_piece(completion: str) -> str:
    """Keep the JSX content up to the first standalone closing ");" of
    the return statement; drop leading comment echo."""
    text = completion
    m = _re.search(r"```(?:jsx|javascript|js)?\s*\n(.*?)```", text, _re.S)
    if m and len(m.group(1)) > 40:
        text = m.group(1)
    lines = text.splitlines()
    # drop leading comment/blank echo
    i = 0
    while i < len(lines) and (not lines[i].strip()
                              or lines[i].strip().startswith("//")):
        i += 1
    kept = []
    for line in lines[i:]:
        stripped = line.strip()
        if stripped == ");" or stripped == ");;":
            break
        kept.append(line)
    body = chr(10).join(kept).rstrip()
    return body + chr(10) + "  );" + chr(10)

def _extract_plain_piece(completion: str, piece: str = "handlers") -> str:
    """Deterministic extraction for non-JSX pieces.

    state: keep code up to the end of the SECOND useEffect block
    (depth-tracked), discarding any handler/JSX run-on bytes.
    handlers: keep code up to the JSX boundary (return ( or <tag).
    The kept bytes are 100% model output."""
    text = completion
    m = _re.search(r"```(?:jsx|javascript|js)?\s*\n(.*?)```", text, _re.S)
    if m and len(m.group(1)) > 40:
        text = m.group(1)
    lines = text.splitlines()

    def jsx_boundary(stripped: str) -> bool:
        return bool(_re.match(r"^return\s*\(", stripped) or
                    _re.match(r"^</?[a-zA-Z]", stripped) or
                    _re.match(r"^\(?<", stripped))

    if piece == "state":
        effect_idx = [i for i, l in enumerate(lines)
                      if "React.useEffect" in l or "useEffect(" in l]
        if len(effect_idx) >= 2:
            start = effect_idx[1]
            depth = 0
            for i in range(start, len(lines)):
                depth += lines[i].count("{") - lines[i].count("}")
                if depth <= 0 and i > start:
                    return chr(10).join(lines[:i + 1]).rstrip() + chr(10)
            return chr(10).join(lines[:start]).rstrip() + chr(10)
        kept = []
        for line in lines:
            stripped = line.strip()
            if jsx_boundary(stripped):
                break
            if _re.match(r"^(async )?function \w+\(", stripped) or \
                    _re.match(r"^const \w+ = (\(|e =>|async)", stripped):
                break
            kept.append(line)
        return chr(10).join(kept).rstrip() + chr(10)

    # handler pieces: the anchor opened a function brace; keep code
    # until the brace depth returns to zero (the piece's own close)
    depth = 1
    kept = []
    for line in lines:
        stripped = line.strip()
        if jsx_boundary(stripped):
            break
        depth += line.count("{") - line.count("}")
        kept.append(line)
        if depth <= 0:
            return chr(10).join(kept).rstrip() + chr(10)
    if depth > 0:
        while kept:
            last = kept[-1].strip()
            balanced = (last.count("(") == last.count(")") and
                        last.count("{") == last.count("}"))
            if balanced and last:
                break
            kept.pop()
        kept.append("  }")
    return chr(10).join(kept).rstrip() + chr(10)

def piece_gate(name: str, body: str) -> str | None:
    if "TODO" in body:
        return "placeholder TODO"
    code = [l for l in body.splitlines()
            if l.strip() and not l.strip().startswith("//")]
    if len(code) < 2:
        return "empty piece"
    # keyword checks must match CODE lines, not echoed spec comments
    code_text = chr(10).join(code)
    if "function App" in body:
        return "redefines App"
    if name == "state":
        for kw in ("useState", "useEffect"):
            if kw not in code_text:
                return f"state missing {kw}"
        if code_text.count("React.useState") > 5:
            return "more than five useState hooks"
        if code_text.count("React.useEffect") != 2:
            return "must have exactly two useEffect"
        if "setOffline(true)" not in code_text:
            return "mount effect must set offline on fetch failure"
    if name in HANDLER_SPECS:
        if len(code) < 2:
            return "handler too short"
        if name == "api" and "res.ok" not in code_text:
            return "api must check res.ok"
        if name == "addProject" and "api/projects" not in code_text:
            return "addProject must POST /api/projects"
        if name == "addTask" and "api/tasks" not in code_text:
            return "addTask must POST /api/tasks"
        if name == "toggle" and "done" not in code_text:
            return "toggle must flip done/todo"
        if name == "editTask" and "prompt(" not in code_text:
            return "editTask must prompt for a new title"
        if name == "removeTask" and "filter" not in code_text:
            return "removeTask must filter the task out"
        if name == "computed" and "doneCount" not in code_text:
            return "computed must define doneCount"
        return None
    if name == "handlers":
        for kw in ("addProject", "addTask", "toggle", "editTask",
                   "removeTask", "prompt", "doneCount", "pct"):
            if kw not in code_text:
                return f"handlers missing {kw}"
        if "res.ok" not in code_text:
            return "must check res.ok"
        if "DEMO_TASKS" not in code_text:
            return "handlers must compute shown from DEMO_TASKS"
        # the handlers must be real functions, not echoed spec text
        n_funcs = len([l for l in code
                       if _re.match(r"\s*(async )?function \w+\(", l)
                       or _re.match(r"\s*const \w+ = (async )?\(", l)])
        if n_funcs < 5:
            return f"only {n_funcs} handler functions (need >= 5)"
    if name == "jsx":
        if "React.useState" in body or "useRef" in body or "useState" in body:
            return "jsx piece must not define hooks"
        first_code = next((l.strip() for l in body.splitlines()
                           if l.strip() and not l.strip().startswith("//")), "")
        if not first_code.startswith("<"):
            return "jsx piece must start with a JSX element"
        for kw in ('className="app"', 'className="sidebar"',
                   'className="progress"', 'className="search"',
                   'className="offline-badge"', 'className="task-row"',
                   'className="project-btn"', 'className="add-form"',
                   'className="toggle"', 'className="edit"',
                   'className="delete"', "filter-all", "filter-done"):
            if kw not in code_text:
                return f"jsx missing {kw}"
        if "DEMO_PROJECTS" not in code_text:
            return "jsx must use DEMO_PROJECTS when offline"
        if "shown" not in code_text:
            return "jsx must render the shown task list"
    return None


def assemble(pieces: dict) -> str:
    src = PIECE_ANCHORS["state"] + pieces.get("state", "")
    if "handlers" in pieces:  # legacy single-piece form
        src += PIECE_ANCHORS["handlers"] + pieces["handlers"]
    for name in HANDLER_PIECES:
        if name in pieces:
            src += PIECE_ANCHORS[name] + pieces[name]
    if "jsx" in pieces:
        src += PIECE_ANCHORS["jsx"] + pieces["jsx"]
    return src + UI_FOOTER


def _jsx_parse_ok(module_source: str) -> bool:
    """esbuild jsx-parse check of a (possibly partial) App module."""
    import subprocess
    import tempfile
    env = dict(os.environ)
    env["NODE_PATH"] = os.environ.get(
        "ARCHAGENT_NODE_PATH", "/home/z/my-project/evalenv/node_modules")
    with tempfile.TemporaryDirectory() as tmp:
        mod = Path(tmp) / "module.jsx"
        mod.write_text(module_source, encoding="utf8")
        chk = Path(tmp) / "check.js"
        chk.write_text(
            "const esbuild=require('esbuild');"
            "try{esbuild.transformSync("
            "require('fs').readFileSync(process.argv[2],'utf8'),"
            "{loader:'jsx',format:'cjs'});console.log('OK')}"
            "catch(e){console.log('ERR '+String(e.message)"
            ".split(String.fromCharCode(10))[0])}", encoding="utf8")
        p = subprocess.run(["node", str(chk), str(mod)],
                           capture_output=True, text=True, timeout=30,
                           env=env, cwd="/home/z/my-project/evalenv")
        return p.stdout.strip().startswith("OK")


MODEL_REF = [None]
HARNESS_LOG_REF = [lambda e: None]


def build_ui(model, harness_log, *, docs=True, wall=1500,
             samples_per_piece=4, resume: dict | None = None,
             on_piece=None) -> dict:
    t0 = time.time()
    pieces: dict[str, str] = dict(resume or {})
    MODEL_REF[0] = model
    HARNESS_LOG_REF[0] = harness_log

    def record(kind, piece, body, usage, seed, accepted, extra=None):
        harness_log({
            "id": f"ui-piece-{piece}-{seed}", "role": "ui",
            "round": f"staged-{piece}", "kind": kind, "seed": seed,
            "stochastic": True, "usage": usage,
            "checks_passed": None, "checks_total": None,
            "syntax_valid": None, "accepted": accepted,
            "origin": {"type": "staged-piece", "piece": piece},
            "source_sha256": sha(body), "source": body,
            "failures": [], "error": None,
            **(extra or {}),
        })

    def burst_piece(name: str, n: int):
        order = ["state"] + HANDLER_PIECES + ["jsx"]
        accepted_before = "".join(pieces.get(m, "") for m in order)
        prompt = piece_prompt(name, accepted_before, docs)
        for k in range(n):
            if time.time() - t0 > wall:
                return None
            seed = 400000 + (int(time.time() * 7) % 89000) + k * 11
            completion, usage = model.generate(
                prompt, max_tokens=1100 if name == "jsx" else 950,
                seed=seed, stochastic=True)
            if _degenerate(completion):
                continue
            body = (_extract_jsx_piece(completion) if name == "jsx"
                    else _extract_plain_piece(completion, name))
            record("staged-piece", name, body, usage, seed, False)
            gate = piece_gate(name, body)
            if gate:
                print(f"  [ui/{name}] sample {k} gate: {gate}", flush=True)
                continue
            if name == "jsx":
                # the complete module can now be fully evaluated
                trial = assemble(pieces | {name: body})
                res = evaluate_module("ui", trial, timeout=60)
                sc = score_of(res)
                if sc[1] and sc[0] == sc[1]:
                    return body, usage, seed
                print(f"  [ui/{name}] sample {k} ui checks {sc[0]}/{sc[1]}",
                      flush=True)
            else:
                # partial piece: structural gate + parse of the partial
                # module (the full evaluation needs all three pieces)
                from archagent.store_builder import _piece_valid
                trial = assemble(pieces | {name: body}) + \
                    "  return null;\n"  # parse-only completion
                # _piece_valid uses js loader; JSX needs the jsx loader:
                if _jsx_parse_ok(trial):
                    return body, usage, seed
                print(f"  [ui/{name}] sample {k} parse fail", flush=True)
        return None

    build_order = (["state"] + HANDLER_PIECES + ["jsx"])
    for name in build_order:
        if name in pieces:
            continue
        if time.time() - t0 > wall:
            break
        got = burst_piece(name, samples_per_piece)
        if got:
            pieces[name], usage, seed = got
            record("staged-piece", name, pieces[name], usage, seed, True)
            if on_piece:
                on_piece(pieces)
            print(f"  [ui/{name}] accepted", flush=True)
        else:
            print(f"  [ui/{name}] no valid sample; skipping", flush=True)

    missing = [m for m in (["state"] + HANDLER_PIECES + ["jsx"])
               if m not in pieces]
    if missing:
        return {"ok": False, "error": f"missing pieces {missing}",
                "pieces": dict(pieces), "partial": True}

    module = assemble(pieces)
    res = evaluate_module("ui", module, timeout=60)
    sc = score_of(res)
    print(f"  [ui] assembled: {sc[0]}/{sc[1]}", flush=True)
    record("staged-assembly", "final", module, {"tokens": 0}, 0,
           sc[0] == sc[1] and sc[1] > 0,
           {"checks_passed": sc[0], "checks_total": sc[1],
            "failures": res.get("failures", [])[:8],
            "error": res.get("error")})
    return {"ok": sc[0] == sc[1] and sc[1] > 0, "source": module,
            "score": sc, "pieces": dict(pieces), "result": res}
