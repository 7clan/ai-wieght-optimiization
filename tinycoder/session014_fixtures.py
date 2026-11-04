"""Frozen, explicit authored web benchmark and disjoint reference trajectories.

These are *custom* React/Express tasks, NOT MBPP or a third-party benchmark.
The five template families per mode are expanded by fixed integer variants.
Generated solutions are never executed in the host interpreter.
"""

from __future__ import annotations

import hashlib
import json

UI_KEYWORDS = ("div", "useEffect", "useState", "render", "component")
BACKEND_KEYWORDS = ("async", "await", "express", "router", "endpoint")
TRIGGER_KEYWORDS = ("def", "class", "async", "return", "if", "for", "while")


def make_web_tasks(*, offset: int = 0):
    if offset not in (0, 25):
        raise ValueError("Only the two frozen web task generations are permitted")
    tasks = []
    for family in range(5):
        for index in range(5):
            n = offset + family * 5 + index
            name = f"UiWidget_{n:02d}"
            if family == 0:
                spec = f"Render an HTML div with data-testid='w{n}' containing the string value prop."
                body = f"    return <div data-testid='w{n}'>{{String(value)}}</div>;\n}}\n"
                tests = [{"props": {"value": v}, "contains": [f'data-testid="w{n}"', str(v)]} for v in ("hello", "world")]
            elif family == 1:
                spec = f"Render an h2 showing the uppercase text prop, prefixed with '{n}:'."
                body = f"    return <h2>{{'{n}:' + String(text).toUpperCase()}}</h2>;\n}}\n"
                tests = [{"props": {"text": v}, "contains": [f"{n}:{v.upper()}", "<h2>"]} for v in ("abc", "xyz")]
            elif family == 2:
                spec = f"Render a ul of items; each li contains the item and has key=index."
                body = "    return <ul>{items.map((item, i) => <li key={i}>{String(item)}</li>)}</ul>;\n}\n"
                tests = [{"props": {"items": items}, "contains": ["<ul>", *[f"<li>{x}</li>" for x in items]]} for items in [["a", "b"], ["x", "y", "z"]]]
            elif family == 3:
                spec = f"Render a button with text 'Action {n}' and disabled={{{{disabled}}}}."
                body = f"    return <button disabled={{disabled}}>Action {n}</button>;\n}}\n"
                tests = [{"props": {"disabled": False}, "contains": [f"Action {n}", "<button"], "not_contains": ["disabled"]},
                         {"props": {"disabled": True}, "contains": [f"Action {n}", "disabled"]}]
            else:
                spec = f"Render a section with strong text 'READY {n}' if ready true, else 'WAIT {n}'."
                body = f"    return <section><strong>{{ready ? 'READY {n}' : 'WAIT {n}'}}</strong></section>;\n}}\n"
                tests = [{"props": {"ready": True}, "contains": [f"READY {n}", "<section>"], "not_contains": [f"WAIT {n}"]},
                         {"props": {"ready": False}, "contains": [f"WAIT {n}", "<section>"], "not_contains": [f"READY {n}"]}]
            props = ("value", "text", "items", "disabled", "ready")[family]
            marker = "// JSX component.\n" if offset == 25 else ""
            prompt = f"const React = require('react');\n{marker}// {spec}\nfunction {name}({{{props}}}) {{\n"
            tasks.append({"task_id": f"WebUI/{n:02d}", "mode": "ui", "family": family,
                          "name": name, "prompt": prompt, "reference": prompt + body,
                          "tests": tests})

    for family in range(5):
        for index in range(5):
            n = offset + family * 5 + index
            name = f"createEndpoint_{n:02d}"
            route = f"/endpoint-{n:02d}"
            common = "    const app = express();\n    app.use(express.json());\n"
            if family == 0:
                spec = f"Create an Express app: GET {route} responds JSON {{message: 'hello-{n}'}}."
                body = common + f"    app.get('{route}', (req,res) => res.json({{message:'hello-{n}'}}));\n"
                tests = [{"method": "get", "path": route, "body": None, "expected": {"message": f"hello-{n}"}}]
            elif family == 1:
                spec = f"Create Express app: POST {route} with JSON a,b responds {{sum:a+b+{n}}}."
                body = common + f"    app.post('{route}', (req,res) => res.json({{sum:Number(req.body.a)+Number(req.body.b)+{n}}}));\n"
                tests = [{"method": "post", "path": route, "body": {"a": a, "b": b}, "expected": {"sum": a+b+n}} for a,b in [(2,3),(-2,4)]]
            elif family == 2:
                spec = f"Create Express app: GET {route}/:id responds JSON {{id: Number(id), tag:'id-{n}'}}."
                body = common + f"    app.get('{route}/:id', (req,res) => res.json({{id:Number(req.params.id),tag:'id-{n}'}}));\n"
                tests = [{"method": "get", "path": f"{route}/{v}", "body": None, "expected": {"id": v, "tag": f"id-{n}"}} for v in (3,17)]
            elif family == 3:
                spec = f"Create Express app: GET {route}?q=... responds JSON {{q: query q or 'none', length: q.length}}."
                body = common + f"    app.get('{route}', (req,res) => {{const q=String(req.query.q || 'none');res.json({{q,length:q.length}});}});\n"
                tests = [{"method": "get", "path": f"{route}?q=abc", "body": None, "expected": {"q": "abc", "length": 3}},
                         {"method": "get", "path": route, "body": None, "expected": {"q": "none", "length": 4}}]
            else:
                spec = f"Create Express app: GET {route} responds JSON {{ok:true, version:{n}}}."
                body = common + f"    app.get('{route}', (req,res) => res.json({{ok:true,version:{n}}}));\n"
                tests = [{"method": "get", "path": route, "body": None, "expected": {"ok": True, "version": n}}]
            body += "    return app;\n}\n"
            prompt = f"const express = require('express');\n// {spec}\nfunction {name}() {{\n"
            tasks.append({"task_id": f"WebAPI/{n:02d}", "mode": "backend", "family": family,
                          "name": name, "prompt": prompt, "reference": prompt + body,
                          "tests": tests})
    assert len(tasks) == 50 and len(set(t["task_id"] for t in tasks)) == 50
    return tasks


def make_reference_trajectories():
    """50 authored clean source examples, disjoint from all web test prompts."""
    trajectories = []
    for n in range(25):
        ui_prompt = ("const React = require('react');\n"
                     f"// Sample DOM component with div, useEffect, useState, render, component, source {n}.\n"
                     f"function TrainingView_{n:02d}({{value}}) {{\n")
        ui_cont = ("    const [shown] = React.useState(value);\n"
                   "    React.useEffect(() => {}, []);\n"
                   f"    const component = <div data-source='ui-{n}'>{{String(shown)}}</div>;\n"
                   "    return component;\n}\n")
        back_prompt = ("const express = require('express');\n"
                       f"// Sample async await express router endpoint, source {n}.\n"
                       f"async function TrainingEndpoint_{n:02d}() {{\n")
        back_cont = ("    const router = express.Router();\n"
                     f"    router.get('/training-{n}', async (req,res) => {{\n"
                     f"        const value = await Promise.resolve({n});\n"
                     "        return res.json({value});\n"
                     "    });\n    return router;\n}\n")
        trajectories.extend([{"mode": "ui", "task_id": f"SourceUI/{n:02d}", "prompt": ui_prompt,
                             "reference": ui_prompt + ui_cont, "name": f"TrainingView_{n:02d}"},
                             {"mode": "backend", "task_id": f"SourceAPI/{n:02d}", "prompt": back_prompt,
                              "reference": back_prompt + back_cont, "name": f"TrainingEndpoint_{n:02d}"}])
    assert len(trajectories) == 50
    return trajectories


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()
