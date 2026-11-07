"""Staged API builder: generate the 10-route TaskFlow Express module one
route at a time (same architecture as the proven store_builder).

Every piece is 100% model bytes; route-signature anchors, assembly and
stub trials are disclosed TRUSTED-SCAFFOLD.  Per-route acceptance = the
route's own API checks passing in a trial where all other routes are
stubbed (registered but answering 500), so a route is only accepted when
ITS contract checks pass against the verified store + logic modules.
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

API_HEADER = ("const express = require('express');\n"
              "function createApi(app, store, processor) {\n"
              "  app.use(express.json());\n")
API_FOOTER = ("}\nmodule.exports = createApi;\n")

# route signature anchors (public contract) in scenario dependency order:
# task routes need projects to exist first; progress needs tasks.
ROUTES = [
    ("health", "  app.get('/api/health', (req, res) => {\n",
     "GET /api/health -> 200 {ok: true}"),
    ("post_project", "  app.post('/api/projects', (req, res) => {\n",
     "POST /api/projects with body {name} -> 201 {project: {...}} or 400"),
    ("get_projects", "  app.get('/api/projects', (req, res) => {\n",
     "GET /api/projects -> 200 {projects: [...]}"),
    ("post_task", "  app.post('/api/tasks', (req, res) => {\n",
     "POST /api/tasks with {projectId, title, priority?} -> 201 {task} or 400"),
    ("put_task", "  app.put('/api/tasks/:id', (req, res) => {\n",
     "PUT /api/tasks/:id with {status?...} -> 200 {task} or 404 or 400"),
    ("get_tasks", "  app.get('/api/tasks', (req, res) => {\n",
     "GET /api/tasks?projectId=&status=&q= -> 200 {tasks: [...]}"),
    ("delete_task", "  app.delete('/api/tasks/:id', (req, res) => {\n",
     "DELETE /api/tasks/:id -> 200 {deleted: true} or 404"),
    ("delete_project", "  app.delete('/api/projects/:id', (req, res) => {\n",
     "DELETE /api/projects/:id -> 200 {deleted: true} or 404"),
    ("progress", "  app.get('/api/projects/:id/progress', (req, res) => {\n",
     "GET /api/projects/:id/progress -> 200 processor({project, tasks}) or 404"),
]

ROUTE_SPECS = {
    "health": """Write the GET /api/health route handler. Write EXACTLY:
  res.status(200).json({ ok: true });
Nothing else.""",
    "post_project": """Write the POST /api/projects route handler. The
store method store.createProject(req.body) returns the new project or
throws Error for invalid input. Write EXACTLY:
  try {
    const project = store.createProject(req.body);
    res.status(201).json({ project: project });
  } catch (e) {
    res.status(400).json({ error: e.message });
  }""",
    "get_projects": """Write the GET /api/projects route handler. Write
EXACTLY:
  res.status(200).json({ projects: store.listProjects() });
Nothing else.""",
    "post_task": """Write the POST /api/tasks route handler. The store
method store.createTask(req.body) returns the new task or throws Error.
Write EXACTLY:
  try {
    const task = store.createTask(req.body);
    res.status(201).json({ task: task });
  } catch (e) {
    res.status(400).json({ error: e.message });
  }""",
    "put_task": """Write the PUT /api/tasks/:id route handler. The store
method store.updateTask(req.params.id, req.body) returns the updated
task, or throws Error. The error message contains 'not found' when the
id is unknown. Write EXACTLY:
  try {
    const task = store.updateTask(req.params.id, req.body);
    res.status(200).json({ task: task });
  } catch (e) {
    if (String(e.message).includes('not found')) {
      res.status(404).json({ error: e.message });
    } else {
      res.status(400).json({ error: e.message });
    }
  }""",
    "get_tasks": """Write the GET /api/tasks route handler. Query params
are in req.query (projectId, status, q — strings or undefined). Write
EXACTLY:
  const filter = {};
  if (req.query.projectId !== undefined) filter.projectId = req.query.projectId;
  if (req.query.status !== undefined) filter.status = req.query.status;
  if (req.query.q !== undefined) filter.q = req.query.q;
  res.status(200).json({ tasks: store.listTasks(filter) });""",
    "delete_task": """Write the DELETE /api/tasks/:id route handler. The
store method store.deleteTask(req.params.id) returns true or throws
Error ('not found' in the message for unknown ids). Write EXACTLY:
  try {
    store.deleteTask(req.params.id);
    res.status(200).json({ deleted: true });
  } catch (e) {
    if (String(e.message).includes('not found')) {
      res.status(404).json({ error: e.message });
    } else {
      res.status(400).json({ error: e.message });
    }
  }""",
    "delete_project": """Write the DELETE /api/projects/:id route handler.
The store method store.deleteProject(req.params.id) returns true or
throws Error ('not found' for unknown ids, and it also deletes the
project's tasks). Write EXACTLY:
  try {
    store.deleteProject(req.params.id);
    res.status(200).json({ deleted: true });
  } catch (e) {
    if (String(e.message).includes('not found')) {
      res.status(404).json({ error: e.message });
    } else {
      res.status(400).json({ error: e.message });
    }
  }""",
    "progress": """Write the GET /api/projects/:id/progress route handler.
The store exposes listProjects() and listTasks({projectId}). The
processor argument is a function: processor({project, tasks}) returns
the progress dict. Write EXACTLY:
  const project = store.listProjects().find(p => p.id === req.params.id);
  if (!project) {
    res.status(404).json({ error: 'project not found: ' + req.params.id });
    return;
  }
  const tasks = store.listTasks({ projectId: req.params.id });
  res.status(200).json(processor({ project: project, tasks: tasks }));""",
}

EXAMPLES = contracts.EXAMPLES["api"]


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


def route_prompt(name: str, anchor: str, docs: bool,
                 accepted: str = "") -> str:
    parts = [_comment(f"NEW TaskFlow API piece: the {name} route. "
                      "Complete the code after the final brace. No prose. "
                      "Shared objects: app (the Express app), store (the "
                      "TaskFlow store), processor (the progress function).")]
    parts.append(_comment(ROUTE_SPECS[name]))
    parts.append(_comment(EXAMPLES))
    if docs:
        parts.append(retrieval.doc_block("api"))
    if accepted:
        parts.append(_comment("Your own accepted routes so far:"))
        parts.append(_comment(accepted[:2000]))
    return "".join(parts) + "\n" + anchor


def _extract_piece(completion: str) -> str:
    """Deterministic cleanup: keep code up to the handler's closing."""
    text = completion
    m = _re.search(r"```(?:javascript|js)?\s*\n(.*?)```", text, _re.S)
    if m and len(m.group(1)) > 15:
        text = m.group(1)
    lines = []
    depth = 1  # inside the arrow function opened by the anchor
    in_str = False
    quote = ""
    i = 0
    seg = text
    # simple brace scan on the whole text, keep until depth returns to 0
    kept_end = None
    while i < len(seg):
        ch = seg[i]
        if in_str:
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in "\"'`":
            in_str = True
            quote = ch
        elif ch == "/" and i + 1 < len(seg) and seg[i + 1] == "/":
            nl = seg.find("\n", i)
            i = nl if nl >= 0 else len(seg)
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                kept_end = i
                break
        i += 1
    body = seg[:kept_end + 1] if kept_end is not None else seg
    body = body.rstrip()
    if not body.endswith("}"):
        body += "\n  }"
    # normalize: the handler is a CALL argument — close with });
    return body + ");\n"


def piece_gate(name: str, body: str) -> str | None:
    if "TODO" in body:
        return "placeholder TODO"
    code = [l for l in body.splitlines()
            if l.strip() and not l.strip().startswith("//")]
    if len(code) < 1:
        return "empty piece"
    if "createApi" in body or "function createApi" in body:
        return "redefines createApi"
    if "store." not in body and name != "health":
        return "does not use the store"
    if name == "progress" and "processor" not in body:
        return "progress must call processor"
    return None


def _route_check_names():
    """Check-name ownership per route (API checks are named by check
    'name' field in API_CHECKS_*)."""
    own = {}
    for c in contracts.API_CHECKS_PUBLIC:
        own.setdefault(c["name"], c)
    return own


CHECK_TO_ROUTE = {
    "health": "health",
    "post_project": "post_project",
    "post_project_invalid": "post_project",
    "get_projects": "get_projects",
    "post_task": "post_task",
    "post_task_invalid": "post_task",
    "put_task": "put_task",
    "put_task_404": "put_task",
    "get_tasks_filter": "get_tasks",
    "get_tasks_search": "get_tasks",
    "delete_task": "delete_task",
    "delete_task_404": "delete_task",
    "progress": "progress",
    "delete_project": "delete_project",
    "progress_404": "progress",
}


def owns_check(check_name: str, route: str) -> bool:
    return CHECK_TO_ROUTE.get(check_name) == route


def stub_assemble(pieces: dict, target: str, candidate: str) -> str:
    src = API_HEADER
    for name, anchor, _ in ROUTES:
        if name in pieces:
            src += anchor + pieces[name]
        elif name == target:
            src += anchor + candidate
        else:
            src += anchor + "    res.status(500).json({ error: 'stub' });\n  });\n"
    return src + API_FOOTER


def assemble(pieces: dict) -> str:
    src = API_HEADER
    for name, anchor, _ in ROUTES:
        if name in pieces:
            src += anchor + pieces[name]
    return src + API_FOOTER


MODEL_REF = [None]
HARNESS_LOG_REF = [lambda e: None]


def build_api(model, harness_log, *, store_source: str, logic_source: str,
              docs=True, wall=1500, samples_per_piece=4,
              resume: dict | None = None, on_piece=None) -> dict:
    t0 = time.time()
    pieces: dict[str, str] = dict(resume or {})
    MODEL_REF[0] = model
    HARNESS_LOG_REF[0] = harness_log

    def record(kind, piece, body, usage, seed, accepted, extra=None):
        harness_log({
            "id": f"api-piece-{piece}-{seed}", "role": "api",
            "round": f"staged-{piece}", "kind": kind, "seed": seed,
            "stochastic": True, "usage": usage,
            "checks_passed": None, "checks_total": None,
            "syntax_valid": None, "accepted": accepted,
            "origin": {"type": "staged-piece", "piece": piece},
            "source_sha256": sha(body), "source": body,
            "failures": [], "error": None,
            **(extra or {}),
        })

    def burst_route(name: str, anchor: str, n: int):
        accepted_so_far = "".join(
            pieces[m] for m, _, _ in ROUTES if m in pieces)
        prompt = route_prompt(name, anchor, docs, accepted_so_far)
        for k in range(n):
            if time.time() - t0 > wall:
                return None
            seed = 500000 + (int(time.time() * 7) % 89000) + k * 11
            completion, usage = model.generate(
                prompt, max_tokens=320, seed=seed, stochastic=True)
            if _degenerate(completion):
                continue
            body = _extract_piece(completion)
            record("staged-piece", name, body, usage, seed, False)
            gate = piece_gate(name, body)
            if gate:
                print(f"  [api/{name}] sample {k} gate: {gate}", flush=True)
                continue
            trial = stub_assemble(pieces, name, body)
            res = evaluate_module("api", trial, store_source=store_source,
                                  logic_source=logic_source, timeout=60)
            mine = {c: ok for c, ok in res.get("checks", {}).items()
                    if owns_check(c, name)}
            if mine and all(mine.values()):
                return body, usage, seed
            bad = [c for c, ok in mine.items() if not ok]
            print(f"  [api/{name}] sample {k} checks fail: {bad[:3]}",
                  flush=True)
        return None

    for name, anchor, _ in ROUTES:
        if name in pieces:
            continue
        if time.time() - t0 > wall:
            break
        got = burst_route(name, anchor, samples_per_piece)
        if got:
            pieces[name], usage, seed = got
            record("staged-piece", name, pieces[name], usage, seed, True)
            if on_piece:
                on_piece(pieces)
            print(f"  [api/{name}] accepted", flush=True)
        else:
            print(f"  [api/{name}] no valid sample; skipping", flush=True)

    missing = [n for n, _, _ in ROUTES if n not in pieces]
    if missing:
        return {"ok": False, "error": f"missing routes {missing}",
                "pieces": dict(pieces), "partial": True}

    module = assemble(pieces)
    res = evaluate_module("api", module, store_source=store_source,
                          logic_source=logic_source, timeout=90)
    sc = score_of(res)
    print(f"  [api] assembled: {sc[0]}/{sc[1]}", flush=True)
    record("staged-assembly", "final", module, {"tokens": 0}, 0,
           sc[0] == sc[1] and sc[1] > 0,
           {"checks_passed": sc[0], "checks_total": sc[1],
            "failures": res.get("failures", [])[:8],
            "error": res.get("error")})
    return {"ok": sc[0] == sc[1] and sc[1] > 0, "source": module,
            "score": sc, "pieces": dict(pieces), "result": res}
