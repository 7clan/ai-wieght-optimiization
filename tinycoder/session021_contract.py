"""Frozen public specification for one coherent Qwen-generated task-board app.

The implementation is never read from the hand-written Orbit reference app.
Only this contract, public examples, and evaluator feedback enter prompts.
Holdout examples must be loaded only after candidate selection is frozen.
"""
from __future__ import annotations

import hashlib
import json


APP_NAME = "FocusBoard"
ROLES = ("logic", "api", "ui", "css")
SPEC = """Build FocusBoard, a small but real task manager with a responsive React UI,
Express JSON API, and Python task statistics. Users can create tasks, view them,
mark them complete/incomplete, delete them, and see total/completed/remaining.
Tasks have id (string), title (nonempty string), priority (low/medium/high),
done (boolean). The trusted harness supplies a persistent SQLite store and
a bridge that invokes your Python transform(payload) function. Do not copy
the implementation from any existing repository file; write the four modules.

API contract:
  GET /api/tasks              -> HTTP 200 {tasks:[...]}
  POST /api/tasks             -> HTTP 201 {task:{id,title,priority,done}}
  PATCH /api/tasks/:id        -> HTTP 200 {task:{id,title,priority,done}}
  DELETE /api/tasks/:id       -> HTTP 200 {deleted:true}
  GET /api/summary            -> HTTP 200 {total,completed,remaining}

The supplied store implements list(), create(body), update(id, body), delete(id).
The supplied processor accepts {tasks: store.list()} and returns the Python
statistics result. The generated Express module must export createApp(store,
processor) returning an Express instance. The generated React App component
must display a task-list heading, an entry form, complete-toggle and delete
buttons, and fetch data from the API. Do not use any external component library.
""".strip()

PUBLIC = [
    {"payload": {"tasks": []}, "expected": {"total": 0, "completed": 0, "remaining": 0}},
    {"payload": {"tasks": [{"done": True}, {"done": False}]},
     "expected": {"total": 2, "completed": 1, "remaining": 1}},
    {"payload": {"tasks": [{"done": True}, {"done": True}, {"done": False}]},
     "expected": {"total": 3, "completed": 2, "remaining": 1}},
]


def holdout():
    return [
        {"payload": {"tasks": [{"done": False}, {"done": False}]},
         "expected": {"total": 2, "completed": 0, "remaining": 2}},
        {"payload": {"tasks": [{"done": True, "title": "One"}]},
         "expected": {"total": 1, "completed": 1, "remaining": 0}},
        {"payload": {"tasks": [{"done": False}, {"done": True},
                                 {"done": False}, {"done": True}]},
         "expected": {"total": 4, "completed": 2, "remaining": 2}},
    ]


def spec_hash():
    return hashlib.sha256(json.dumps({"spec": SPEC, "public": PUBLIC},
                                     sort_keys=True).encode()).hexdigest()


def prompt(role):
    common = f"# FocusBoard public specification:\n" + "\n".join(
        "# " + row for row in SPEC.splitlines())
    if role == "logic":
        return (common + "\n# backend/logic.py Python 3.11.\n"
                "# Return exactly {total:int,completed:int,remaining:int}.\n"
                "# Count done=True as completed. No external libraries.\n"
                "def transform(payload):\n")
    if role == "api":
        comment = "\n".join("// " + row for row in SPEC.splitlines())
        return ("const express = require('express');\n" + comment + "\n"
                "// server/routes.js. No database or other imports.\n"
                "function createApp(store, processor) {\n"
                "  const app = express();\n"
                "  app.use(express.json());\n")
    if role == "ui":
        comment = "\n".join("// " + row for row in SPEC.splitlines())
        return ("const React = require('react');\n"
                "const {useEffect, useState} = React;\n" + comment + "\n"
                "// client/App.jsx. React hooks and fetch are available.\n"
                "function App() {\n")
    if role == "css":
        return ("/* client/style.css: modern responsive FocusBoard task-manager styles.\n"
                "   Use only CSS, no scripts or external URLs. */\n"
                "body {\n")
    raise ValueError(role)
