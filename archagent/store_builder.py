"""Staged store builder: generate the 8-method TaskFlow store one piece at
a time (mission section 6: "Do not ask Qwen to generate the entire
application in one completion").

Measured rationale: the frozen 0.5B model reliably solves ~15-line
completions (the logic module passed via burst sampling) but cannot
produce a valid 49-line 8-method module in one shot (32 whole-module
attempts: best 7/24, most syntactically invalid).  Each staged piece is a
small anchored completion; the harness assembles them deterministically.

Every piece is 100% model bytes; the assembly, anchors and the final
return-object footer are disclosed TRUSTED-SCAFFOLD.  Failure feedback
maps back to the owning method, which is re-burst with its own spec plus
the feedback (bounded repair waves).
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
                              _post_process, _degenerate)

from archagent.contracts import STORE_SCENARIO_PUBLIC as SCENARIO_STEPS

def _persistence_probe(module_source: str) -> bool:
    """Construct the store against a pre-written db.json containing one
    project; listProjects must return it (the load must run)."""
    import subprocess
    import tempfile
    env = dict(os.environ)
    env["NODE_PATH"] = os.environ.get(
        "ARCHAGENT_NODE_PATH", "/home/z/my-project/evalenv/node_modules")
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "db.json")
        with open(db, "w") as f:
            json.dump({"projects": [{"id": "p1", "name": "X",
                                     "createdAt": "2026-11-07"}],
                       "tasks": []}, f)
        mod = os.path.join(tmp, "store.js")
        with open(mod, "w") as f:
            f.write(module_source)
        t = os.path.join(tmp, "probe.js")
        with open(t, "w") as f:
            f.write(
                "const createStore = require(" + json.dumps(mod) + ");\n"
                "const s = createStore(" + json.dumps(db) + ");\n"
                "const ps = s.listProjects();\n"
                "console.log(ps && ps.length === 1 && ps[0].id === 'p1' "
                "? 'PROBE OK' : 'PROBE FAIL ' + JSON.stringify(ps));")
        p = subprocess.run(["node", t], capture_output=True, text=True,
                           timeout=30, env=env,
                           cwd="/home/z/my-project/evalenv")
        return p.stdout.strip().startswith("PROBE OK")


MODEL_REF = [None]
HARNESS_LOG_REF = [lambda e: None]
piece_gate_ref = [lambda p, b: "not initialized"]


def piece_gate(piece: str, body: str) -> str | None:
    """Structural gates applied to every staged piece."""
    if "TODO" in body:
        return "placeholder TODO"
    code_lines = [l for l in body.splitlines()
                  if l.strip() and not l.strip().startswith("//")]
    if len(code_lines) < 2:
        return "empty/comment-only piece"
    if "createStore(" in body:
        return "calls createStore inside the store"
    # a method must never redeclare the shared state (shadowing makes it
    # return empty data forever)
    if _re.search(r"\b(?:let|const)\s+state\s*=", body):
        return "redeclares state (shadowing)"
    if piece == "stateA":
        for kw in ("existsSync", "JSON"):
            if kw not in body:
                return f"stateA missing {kw}"
        # the load must RUN at construction, not just be defined
        if _re.search(r"(function\s+load|let\s+load\s*=|const\s+load\s*=)", body):
            if not _re.search(r"load\(\)", body):
                return "load is defined but never called"
        for m in METHOD_ORDER:
            if f"function {m}" in body:
                return f"state piece defines method {m}"
        code = [l for l in body.splitlines()
                if l.strip() and not l.strip().startswith("//")]
        if len(code) > 20:
            return f"state piece too long ({len(code)} code lines > 20)"
        if not _re.search(r"let\s+pnext\s*=", body):
            return "pnext must be a let variable (let pnext = ...)"
        if not _re.search(r"let\s+tnext\s*=", body):
            return "tnext must be a let variable (let tnext = ...)"
    base = piece.split("-")[0]
    if base in ("createProject", "createTask"):
        if "push" not in body:
            return "create must push into the array"
        if "save" not in body:
            return "create must call save()"
    if base in ("updateProject", "updateTask", "deleteProject", "deleteTask"):
        if "save" not in body:
            return "mutation must call save()"
    return None


HEADER = "const fs = require('node:fs');\nfunction createStore(filePath) {\n"
FOOTER = ("  return { listProjects, createProject, updateProject, "
          "deleteProject,\n           listTasks, createTask, updateTask, "
          "deleteTask };\n}\nmodule.exports = createStore;\n")

STATE_A_SPEC = """Write the FIRST PART of the state setup for the TaskFlow
store (inside function createStore(filePath)). Write EXACTLY these three
things and NOTHING else:
1. exactly: let state = { projects: [], tasks: [] };
   The empty default MUST have BOTH keys as arrays — never null, never
   {}, never missing a key.
2. then only when fs.existsSync(filePath) is true, replace it:
   if (fs.existsSync(filePath)) {
     state = JSON.parse(fs.readFileSync(filePath, 'utf8'));
   }
3. exactly two counter lines:
   let pnext = 1;
   let tnext = 1;
   (advanced later by the create methods; do not compute from loaded
   data — just start at 1)
FORBIDDEN: no other functions, no save(), no return, no methods.
Roughly 6-8 lines total."""

STATE_B_SPEC = """Write the save() helper for the TaskFlow store (it
already has: let state = {...}; let pnext = 1; let tnext = 1;).
Write EXACTLY one function:
  function save() {
    fs.writeFileSync(filePath, JSON.stringify(state));
  }
Nothing else. No return, no other functions, no methods."""

SAVE_ANCHOR = "  function save() {\n"

METHOD_SPECS = {
    "listProjects": """Write the listProjects() method for the TaskFlow
store. The shared state variable is named state; all projects live in
state.projects (an array). Return exactly:
state.projects.map(p => ({ ...p }))
so callers get copies and cannot mutate internal state. No parameters.""",
    "createProject": """
Write the createProject(body) method for the TaskFlow store. Shared
variables: state, save() — never s.projects or s.save(). body is {name}.
Write EXACTLY this method body:
  if (typeof body.name !== 'string' || !body.name) {
    throw Error('invalid name');
  }
  const project = { id: 'p' + (pnext++), name: body.name,
                    createdAt: '2026-11-07' };
  state.projects.push(project);
  save();
  return { ...project };
The returned object has EXACTLY the keys id, name, createdAt.""",
    "updateProject": """
Write the updateProject(id, body) method for the TaskFlow store. Shared
variables: state, save(). Write EXACTLY this method body:
  const project = state.projects.find(p => p.id === String(id));
  if (!project) throw Error('project not found: ' + id);
  if (body.name !== undefined) {
    if (typeof body.name !== 'string' || !body.name) {
      throw Error('invalid name');
    }
    project.name = body.name;
  }
  save();
  return { ...project };""",
    "deleteProject": """Write the deleteProject(id) method for the TaskFlow store. Shared
variables: state, save(). First:
  const project = state.projects.find(p => p.id === String(id));
  if (!project) throw Error('project not found: ' + id);
Then remove the project from state.projects AND remove every task whose
projectId equals String(id) from state.tasks. Call save() and return
true.""",
    "listTasks": """Write the listTasks(filter) method for the TaskFlow store. Shared
variable: state. filter is {projectId?, status?, q?} (may be undefined —
default to {}). Start from state.tasks; when filter.projectId is
provided keep only tasks with that exact projectId; when filter.status
is provided keep only that exact status; when filter.q is a non-empty
string keep only tasks whose title contains it case-insensitively
(title.toLowerCase().includes(q.toLowerCase())). Missing or empty keys
match everything. Return the matches as COPIES:
  return matches.map(t => ({ ...t }));""",
    "createTask": """
Write the createTask(body) method for the TaskFlow store. Shared
variables: state, save(). body is {projectId, title, priority?, status?}.
Write EXACTLY this method body:
  if (!state.projects.some(p => p.id === String(body.projectId))) {
    throw Error('project not found: ' + body.projectId);
  }
  if (typeof body.title !== 'string' || !body.title) {
    throw Error('invalid title');
  }
  const priority = body.priority === undefined ? 'medium' : body.priority;
  const status = body.status === undefined ? 'todo' : body.status;
  if (!['low', 'medium', 'high'].includes(priority)) {
    throw Error('invalid priority');
  }
  if (!['todo', 'doing', 'done'].includes(status)) {
    throw Error('invalid status');
  }
  const task = { id: 't' + (tnext++), projectId: String(body.projectId),
                 title: body.title, priority: priority, status: status,
                 createdAt: '2026-11-07' };
  state.tasks.push(task);
  save();
  return { ...task };""",
    "updateTask": """
Write the updateTask(id, body) method for the TaskFlow store. Shared
variables: state, save(). Write EXACTLY this method body:
  const task = state.tasks.find(t => t.id === String(id));
  if (!task) throw Error('task not found: ' + id);
  if (body.title !== undefined) {
    if (typeof body.title !== 'string' || !body.title) {
      throw Error('invalid title');
    }
    task.title = body.title;
  }
  if (body.priority !== undefined) {
    if (!['low', 'medium', 'high'].includes(body.priority)) {
      throw Error('invalid priority');
    }
    task.priority = body.priority;
  }
  if (body.status !== undefined) {
    if (!['todo', 'doing', 'done'].includes(body.status)) {
      throw Error('invalid status');
    }
    task.status = body.status;
  }
  save();
  return { ...task };""",
    "deleteTask": """Write the deleteTask(id) method for the TaskFlow store. Shared
variables: state, save(). First:
  const task = state.tasks.find(t => t.id === String(id));
  if (!task) throw Error('task not found: ' + id);
Remove it from state.tasks, call save(), return true.""",
}

METHOD_ANCHOR = {
    "listProjects": "  function listProjects() {\n",
    "createProject": "  function createProject(body) {\n",
    "updateProject": "  function updateProject(id, body) {\n",
    "deleteProject": "  function deleteProject(id) {\n",
    "listTasks": "  function listTasks(filter) {\n",
    "createTask": "  function createTask(body) {\n",
    "updateTask": "  function updateTask(id, body) {\n",
    "deleteTask": "  function deleteTask(id) {\n",
}

# build order respects scenario dependencies: listTasks's checks count
# tasks created by createTask, so createTask (+ its dependencies) must be
# real before listTasks can pass its acceptance trial
METHOD_ORDER = ["listProjects", "createProject", "createTask",
                "updateProject", "updateTask", "deleteProject",
                "deleteTask", "listTasks"]

EXAMPLES = contracts.EXAMPLES["store"]


def _js_dumps(obj) -> str:
    """json.dumps with JS JSON.stringify spacing (no spaces)."""
    return json.dumps(obj, separators=(",", ":"))


def _scenario_check_names(steps):
    """Replicate the worker's check naming (including dedupe) to know
    which checks exist before the first reload op."""
    names = []
    seen = {}
    for step in steps:
        if step.get("op") == "reload":
            break
        name = step["op"]
        if step.get("id"):
            name += ":" + str(step["id"])
        if step.get("body") is not None:
            name += ":" + _js_dumps(step["body"])[:40]
        if step.get("filter") is not None:
            name += ":" + _js_dumps(step["filter"])[:40]
        n = seen.get(name, 0)
        seen[name] = n + 1
        if n:
            name += f"#{n + 1}"
        names.append(name)
    return names


def _owns_check(name: str, target: str) -> bool:
    """A check belongs to method target iff its op part is exactly the
    method name (check names are 'op' or 'op:<suffix>')."""
    return name == target or name.startswith(target + ":")


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


def state_prompt(docs: bool) -> str:
    parts = [_comment("NEW TaskFlow STORE piece 1/9: state setup. "
                      "Complete the code after the final brace. No prose.")]
    parts.append(_comment(STATE_SPEC))
    parts.append(_comment(EXAMPLES))
    if docs:
        parts.append(retrieval.doc_block("store"))
    return "".join(parts) + "\n" + HEADER


def method_prompt(name: str, accepted_state: str, accepted_methods: str,
                  docs: bool, feedback: str = "") -> str:
    parts = [_comment(f"NEW TaskFlow STORE piece: the {name} method. "
                      "Complete the code after the final brace. No prose. "
                      "You are INSIDE createStore: never call createStore, "
                      "never create a store variable; use the state and "
                      "save() helper from your accepted setup code below.")]
    parts.append(_comment(METHOD_SPECS[name]))
    parts.append(_comment("Your own accepted store code so far (state + "
                          "other methods already written):"))
    parts.append(_comment(accepted_state + accepted_methods))
    parts.append(_comment(EXAMPLES))
    if docs:
        parts.append(retrieval.doc_block("store"))
    if feedback:
        parts.append(_comment("PUBLIC CHECK FEEDBACK for this method: "
                              + feedback[:400]))
        parts.append(_comment("Rewrite the method so its checks pass; keep "
                              "the same function signature."))
    return "".join(parts) + "\n" + METHOD_ANCHOR[name]


def _extract_piece(completion: str) -> str:
    """Deterministic cleanup: the completion is the body after the anchor's
    opening brace; close it with a single brace line.  Strip fenced blocks
    and trailing prose."""
    text = completion
    m = _re.search(r"```(?:javascript|js)?\s*\n(.*?)```", text, _re.S)
    if m and len(m.group(1)) > 20:
        text = m.group(1)
    # cut at the first line that is clearly prose after a closed brace
    lines = []
    depth = 1  # we are inside the anchor's opening brace
    for line in text.splitlines():
        if not line.strip():
            lines.append(line)
            continue
        stripped = line.strip()
        depth += stripped.count("{") - stripped.count("}")
        lines.append(line)
        if depth <= 0:
            break
    body = "\n".join(lines).rstrip()
    if not body.endswith("}"):
        body += "\n  }"
    else:
        # ensure the closing brace is at the right indent
        body = body[:body.rfind("}")].rstrip() + "\n  }"
    return body + "\n"


def _piece_valid(module_source: str) -> bool:
    """esbuild-parse check of the assembled module SOURCE TEXT."""
    import subprocess
    import tempfile
    env = dict(os.environ)
    env["NODE_PATH"] = os.environ.get(
        "ARCHAGENT_NODE_PATH", "/home/z/my-project/evalenv/node_modules")
    with tempfile.TemporaryDirectory() as tmp:
        mod = Path(tmp) / "module.js"
        mod.write_text(module_source, encoding="utf8")
        check_js = Path(tmp) / "check.js"
        check_js.write_text(
            "const esbuild=require('esbuild');"
            "try{esbuild.transformSync("
            "require('fs').readFileSync(process.argv[2],'utf8'),"
            "{loader:'js',format:'cjs'});console.log('OK')}"
            "catch(e){console.log('ERR '+String(e.message)"
            ".split(String.fromCharCode(10))[0])}", encoding="utf8")
        proc = subprocess.run(
            ["node", str(check_js), str(mod)], capture_output=True,
            text=True, timeout=30, env=env,
            cwd="/home/z/my-project/evalenv")
        return proc.stdout.strip().startswith("OK")


def _cut_at_method_boundary(text: str) -> str:
    """Deterministic extraction on the RAW completion: cut at the first
    staged-method definition, then trim so the piece ends INSIDE
    createStore (brace depth exactly 1).  Never adds or rewrites model
    bytes; only discards bytes after the boundary and at most the one
    closing brace that would close createStore itself."""
    cut = len(text)
    for m in METHOD_ORDER:
        for pat in (f"function {m}", f"  {m}:", f"  {m}("):
            idx = text.find(pat)
            if 0 <= idx < cut:
                cut = idx
    segment = text[:cut]
    # depth scan: the anchor 'function createStore(filePath) {' left us at
    # depth 1; ignore braces inside strings/comments approximately
    depth = 1
    in_str = False
    quote = ""
    i = 0
    last_close_at = -1
    while i < len(segment):
        ch = segment[i]
        if in_str:
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in "\"'`":
            in_str = True
            quote = ch
        elif ch == "/" and i + 1 < len(segment) and segment[i + 1] == "/":
            nl = segment.find("\n", i)
            i = nl if nl >= 0 else len(segment)
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_close_at = i
        i += 1
    if last_close_at >= 0:
        segment = segment[:last_close_at].rstrip()
    return segment.rstrip() + "\n"


def _state_a_prompt(docs: bool) -> str:
    parts = [_comment("NEW TaskFlow STORE piece: state + load + counters. "
                      "Complete the code after the final brace. No prose.")]
    parts.append(_comment(STATE_A_SPEC))
    if docs:
        parts.append(retrieval.doc_block("store"))
    return "".join(parts) + "\n" + HEADER


def _state_b_prompt(docs: bool, accepted_a: str) -> str:
    parts = [_comment("NEW TaskFlow STORE piece: the save() helper. "
                      "Complete the code after the final brace. No prose. "
                      "The state variable and counters already exist; do "
                      "NOT redeclare them — write ONLY save()'s body.")]
    parts.append(_comment(STATE_B_SPEC))
    return "".join(parts) + "\n" + SAVE_ANCHOR


def _extract_save_piece(completion: str) -> str:
    """save() completion: keep the writeFileSync line and close."""
    text = completion
    m = _re.search(r"```(?:javascript|js)?\s*\n(.*?)```", text, _re.S)
    if m and len(m.group(1)) > 10:
        text = m.group(1)
    lines = []
    for line in text.splitlines():
        lines.append(line)
        if "}" in line:
            break
    body = "\n".join(lines).rstrip()
    if not body.endswith("}"):
        body += "\n  }"
    return body + "\n"


def burst_state_bounded(docs: bool, n: int = 4,
                        current_pieces: dict | None = None,
                        on_state=None):
    """Two mini-pieces: (A) state+load+counters via boundary-cut
    extraction, (B) save() helper.  Returns (stateA, saveB, usage, seed)
    or None.  on_state(stateA_or_None, saveB_or_None) checkpoints each
    accepted piece immediately so later failures never lose it."""
    cp = current_pieces or {}

    def log_piece(piece, seed, usage, body, raw):
        HARNESS_LOG_REF[0]({
            "id": f"store-piece-{piece}-{seed}", "role": "store",
            "round": f"staged-{piece}", "kind": "staged-piece",
            "seed": seed, "stochastic": True, "usage": usage,
            "checks_passed": None, "checks_total": None,
            "syntax_valid": None, "accepted": False,
            "origin": {"type": "staged-piece", "piece": piece,
                       "raw_completion": raw},
            "source_sha256": sha(body), "source": body,
            "failures": [], "error": None,
        })

    # ---- piece A (resume from checkpoint when present) ----
    state_a = cp.get("stateA")
    if state_a:
        print("  [store/stateA] resumed from checkpoint", flush=True)
    else:
        for k in range(n):
            seed = 600000 + (int(time.time() * 7) % 89000) + k * 11
            completion, usage = MODEL_REF[0].generate(
                _state_a_prompt(docs), max_tokens=360,
                seed=seed, stochastic=True)
            if _degenerate(completion):
                continue
            body = _extract_state_a(completion)
            log_piece("stateA", seed, usage, body, completion)
            gate = piece_gate_ref[0]("stateA", body)
            if gate:
                print(f"  [store/stateA] sample {k} gate: {gate}",
                      flush=True)
                continue
            # parse check: the piece must form a valid module with stubs
            trial_a = HEADER + body + "".join(
                f"  function {m}() {{ throw Error('x'); }}\n"
                for m in METHOD_ORDER) + FOOTER
            if not _piece_valid(trial_a):
                print(f"  [store/stateA] sample {k} parse fail",
                      flush=True)
                continue
            state_a = body
            if on_state:
                on_state(state_a, None)
            print("  [store/stateA] accepted", flush=True)
            break
    if state_a is None:
        return None

    # ---- piece B (save; resume from checkpoint when present) ----
    save_b = cp.get("stateB")
    if save_b:
        print("  [store/stateB] resumed from checkpoint", flush=True)
        return state_a, save_b, {"tokens": 0}, 0
    for k in range(n):
        seed = 650000 + (int(time.time() * 7) % 89000) + k * 11
        completion, usage = MODEL_REF[0].generate(
            _state_b_prompt(docs, state_a), max_tokens=160,
            seed=seed, stochastic=True)
        body = _extract_save_piece(completion)
        log_piece("stateB", seed, usage, body, completion)
        if "writeFileSync" not in body or "TODO" in body:
            print(f"  [store/stateB] sample {k} gate: bad save", flush=True)
            continue
        if "filePath" not in body or "'./" in body or '"./' in body:
            print(f"  [store/stateB] sample {k} gate: must use the "
                  f"filePath parameter", flush=True)
            continue
        # combined trial with listProjects gating
        combined = state_a + SAVE_ANCHOR + body
        trial = HEADER + combined
        for m in METHOD_ORDER:
            trial += (METHOD_ANCHOR[m] + cp[m]) if m in cp else (
                f"  function {m}() {{ throw Error('not implemented'); }}\n")
        trial += FOOTER
        if not _piece_valid(trial):
            print(f"  [store/stateB] sample {k} parse fail", flush=True)
            continue
        if "listProjects" in cp:
            res = evaluate_module("store", trial, timeout=45)
            pre = set(_scenario_check_names(SCENARIO_STEPS))
            mine = {x: ok for x, ok in res.get("checks", {}).items()
                    if _owns_check(x, "listProjects") and x in pre}
            if not (mine and all(mine.values())):
                print(f"  [store/stateB] sample {k} listProjects fail",
                      flush=True)
                continue
            # persistence probe: a pre-written db.json must load
            probe_ok = _persistence_probe(trial)
            if not probe_ok:
                print(f"  [store/stateB] sample {k} persistence probe fail"
                      f" (load does not run at construction)", flush=True)
                continue
        if on_state:
            on_state(None, body)
        return state_a, body, usage, seed
    return None


def _cut_at_save_boundary(body: str) -> str:
    """Also cut at a save() definition (piece B owns save)."""
    for pat in ("function save", "save =", "const save"):
        idx = body.find(pat)
        if idx >= 0:
            out = body[:idx].rstrip()
            while out.endswith("}"):
                out = out[:out.rfind("}")].rstrip()
            return out + "\n"
    return body


def _extract_state_a(raw_completion: str) -> str:
    """Deterministic extraction of the stateA piece from a raw completion:
    (1) drop the leading comment-echo block (the model echoes the spec);
    (2) keep code lines only up to the first return statement or function
    definition (stateA must contain neither).  The kept bytes are 100%
    model output; the rule only discards echo and run-on bytes."""
    lines = raw_completion.splitlines()
    # drop leading comment/blank block
    i = 0
    while i < len(lines) and (not lines[i].strip()
                              or lines[i].strip().startswith("//")):
        i += 1
    kept = []
    for line in lines[i:]:
        stripped = line.strip()
        if stripped.startswith(("return ", "return(", "function ",
                                "const fn", "async ")):
            break
        kept.append(line)
    # depth-scan: drop only the brace that would close createStore
    # (depth 0); inner blocks keep their closing braces
    text = "\n".join(kept)
    depth = 1
    in_str = False
    quote = ""
    cut = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in "\"'`":
            in_str = True
            quote = ch
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            nl = text.find("\n", i)
            i = nl if nl >= 0 else len(text)
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                cut = i
                break
        i += 1
    if cut is not None:
        text = text[:cut]
    return text.rstrip() + "\n"


def build_store(model, harness_log, *, docs=True, wall=1500,
                samples_per_piece=4, repair_waves=3,
                resume: dict | None = None, on_piece=None) -> dict:
    """Run the staged build; returns the final module + provenance.

    resume: previously accepted pieces {piece_name: source}; the build
    continues from there.  on_piece(name) is called after each acceptance
    for checkpointing."""
    t0 = time.time()
    pieces: dict[str, str] = dict(resume or {})
    MODEL_REF[0] = model
    HARNESS_LOG_REF[0] = harness_log
    piece_gate_ref[0] = piece_gate

    def record(kind, piece, completion, usage, seed, accepted, extra=None):
        entry = {
            "id": f"store-piece-{piece}-{seed}", "role": "store",
            "round": f"staged-{piece}", "kind": kind, "seed": seed,
            "stochastic": True, "usage": usage,
            "checks_passed": None, "checks_total": None,
            "syntax_valid": None, "accepted": accepted,
            "origin": {"type": "staged-piece", "piece": piece},
            "source_sha256": sha(completion), "source": completion,
            "failures": [], "error": None,
            **(extra or {}),
        }
        harness_log(entry)

    def check_names_for(piece):
        if piece.startswith("state"):
            return ("reload", "persistedShape")
        return (piece.split("-")[0],)

    def stub_assemble(current: dict, target: str, candidate: str) -> str:
        s = HEADER + (current.get("state") or
                      "  let state = { projects: [], tasks: [] };\n"
                      "  function save() {}\n")
        for name in METHOD_ORDER:
            if name in current:
                s += METHOD_ANCHOR[name] + current[name]
            elif name == target:
                s += METHOD_ANCHOR[name] + candidate
            else:
                s += (f"  function {name}() {{ throw Error("
                      f"'not implemented'); }}\n")
        return s + FOOTER

    def burst_piece(prompt, piece, n, accepted_required=True):
        """Burst samples; accept the first that passes the structural gate
        AND makes its own scenario checks pass in stub-trial evaluation."""
        target = piece.split("-")[0]
        trial_pieces = dict(pieces)
        best = None
        for k in range(n):
            if time.time() - t0 > wall:
                break
            seed = 700000 + (hash(piece) % 90000) + k * 7 + \
                int(time.time() * 10) % 997
            completion, usage = model.generate(
                prompt, max_tokens=420, seed=seed, stochastic=True)
            if _degenerate(completion):
                continue
            body = _extract_piece(completion)
            record("staged-piece", piece, body, usage, seed, False)
            gate = piece_gate(piece, body)
            if gate:
                print(f"  [store/{piece}] sample {k} gate: {gate}", flush=True)
                continue
            if target in METHOD_ORDER:
                trial = stub_assemble(trial_pieces, target, body)
                res = evaluate_module("store", trial, timeout=45)
                pre = set(_scenario_check_names(SCENARIO_STEPS))
                mine = {name: ok for name, ok in res.get("checks", {}).items()
                        if _owns_check(name, target) and name in pre}
                if mine and all(mine.values()):
                    return body, usage, seed
                bad = [name for name, ok in mine.items() if not ok]
                print(f"  [store/{piece}] sample {k} checks fail: "
                      f"{bad[:3]}", flush=True)
            else:
                return body, usage, seed
        return None

    def assemble(current: dict) -> str:
        src = HEADER + (current.get("state", "") or "")
        for name in METHOD_ORDER:
            if name in current:
                src += METHOD_ANCHOR[name] + current[name]
        return src + FOOTER

    # stage 0: listProjects first (no state dependency) so the state
    # piece can be gated on its checks
    if "listProjects" not in pieces:
        prompt = method_prompt("listProjects",
                               "let state = { projects: [], tasks: [] };\n"
                               "function save() {}\n", "", docs)
        got = burst_piece(prompt, "listProjects", samples_per_piece)
        if got:
            pieces["listProjects"], usage, seed = got
            record("staged-piece", "listProjects", pieces["listProjects"],
                   usage, seed, True)
            if on_piece:
                on_piece(pieces)
            print("  [store/listProjects] accepted", flush=True)

    # stage 1: state setup.  The model reliably writes the correct setup
    # as the PREFIX of its completion and then runs on into methods, so
    # the deterministic extraction cuts at the first method boundary —
    # the extracted bytes are 100% model output (same class as cutting
    # trailing prose; disclosed TRUSTED-SCAFFOLD extraction rule).
    if "state" not in pieces:
        def state_checkpoint(state_a, save_b):
            if state_a is not None:
                pieces["stateA"] = state_a
            if save_b is not None:
                pieces["stateB"] = save_b
            if on_piece:
                on_piece(pieces)
        got = burst_state_bounded(docs, samples_per_piece,
                                  current_pieces=pieces,
                                  on_state=state_checkpoint)
        if not got:
            return {"ok": False, "error": "state pieces never valid",
                    "pieces": dict(pieces)}
        state_a, save_b, usage, seed = got
        pieces["state"] = state_a + SAVE_ANCHOR + save_b
        record("staged-piece", "stateA", state_a, usage, seed, True)
        record("staged-piece", "stateB", save_b, usage, seed, True)
        if on_piece:
            on_piece(pieces)
        print(f"  [store/state] accepted "
              f"({len(pieces['state'].splitlines())} lines)", flush=True)
    else:
        print("  [store/state] resumed", flush=True)

    # stages 2-9: remaining methods
    for name in METHOD_ORDER:
        if name == "listProjects":
            continue
        if name in pieces:
            continue
        if time.time() - t0 > wall:
            break
        accepted_state = pieces.get("state", "")
        accepted_methods = "".join(pieces.get(m, "") for m in METHOD_ORDER)
        prompt = method_prompt(name, accepted_state, accepted_methods, docs)
        got = burst_piece(prompt, name, samples_per_piece)
        if not got:
            print(f"  [store/{name}] no valid sample; skipping", flush=True)
            continue
        pieces[name], usage, seed = got
        record("staged-piece", name, pieces[name], usage, seed, True)
        if on_piece:
            on_piece(pieces)
        print(f"  [store/{name}] accepted", flush=True)

    # full evaluation + bounded per-method repair waves
    missing = [m for m in METHOD_ORDER if m not in pieces]
    if missing:
        return {"ok": False, "error": f"budget exhausted; missing {missing}",
                "pieces": dict(pieces), "partial": True}
    for wave in range(repair_waves):
        module = assemble(pieces)
        result = evaluate_module("store", module, timeout=60)
        sc = score_of(result)
        print(f"  [store] assembled wave {wave}: {sc[0]}/{sc[1]}", flush=True)
        record("staged-assembly", f"wave{wave}", module, {"tokens": 0}, 0,
               sc[0] == sc[1] and sc[1] > 0,
               {"checks_passed": sc[0], "checks_total": sc[1],
                "failures": result.get("failures", [])[:8],
                "error": result.get("error")})
        if sc[1] and sc[0] == sc[1]:
            return {"ok": True, "source": module, "score": sc,
                    "pieces": dict(pieces), "result": result}
        if time.time() - t0 > wall:
            break
        # map failures to methods and re-burst the worst offenders
        failed_ops = set()
        for f in result.get("failures", []):
            op = f.get("check", "").split(":")[0].split("{")[0]
            failed_ops.add(op.strip())
        repaired_any = False
        for op in sorted(failed_ops):
            target = {"createProject": "createProject",
                      "updateProject": "updateProject",
                      "deleteProject": "deleteProject",
                      "listTasks": "listTasks", "createTask": "createTask",
                      "updateTask": "updateTask", "deleteTask": "deleteTask",
                      "listProjects": "listProjects"}.get(op)
            if not target or target not in pieces:
                continue
            if time.time() - t0 > wall:
                break
            feedback = "; ".join(
                f"{f['check']}: {f['detail']}" for f in
                result.get("failures", [])
                if f["check"].split(":")[0].split("{")[0].strip() == op)[:400]
            accepted_state = pieces.get("state", "")
            accepted_methods = "".join(
                pieces.get(m, "") for m in METHOD_ORDER if m != target)
            prompt = method_prompt(target, accepted_state, accepted_methods,
                                   docs, feedback=feedback)
            got = burst_piece(prompt, f"{target}-fix{wave}",
                              samples_per_piece)
            if got:
                new_body = got[0]
                if new_body != pieces[target]:
                    pieces[target] = new_body
                    repaired_any = True
                    record("staged-piece", f"{target}-fix{wave}", new_body,
                           got[1], got[2], True)
                    print(f"  [store/{target}] repaired (wave {wave})",
                          flush=True)
        if not repaired_any:
            break

    module = assemble(pieces)
    result = evaluate_module("store", module, timeout=60)
    return {"ok": score_of(result)[0] == score_of(result)[1] > 0,
            "source": module, "score": score_of(result),
            "pieces": dict(pieces), "result": result}
