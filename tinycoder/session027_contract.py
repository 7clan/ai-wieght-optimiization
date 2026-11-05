"""Frozen fresh-app contract: PocketLedger, NOT the earlier FocusBoard task board.

Keep the independently authored holdout examples inaccessible until all model
generation and public candidate selection are complete.
"""
from __future__ import annotations

import hashlib
import json

NAME = "PocketLedger"
ROLES = ("logic", "store", "api", "ui", "css")
SPEC = """Build PocketLedger: a small personal expense tracker. This is a NEW
application, not FocusBoard. Users can add expenses, browse and remove them,
and see category totals. Use React, Express and Python 3.11, plus an on-disk
JSON store in Node.js. Implement the actual application code in five modules.
There is no task-completion or status-toggle feature.

Expense fields: id (string), description (nonempty string),
amount_cents (positive integer), category (food, travel or other).

API:
  GET /api/expenses           -> HTTP 200 {expenses:[...]}
  POST /api/expenses          -> HTTP 201 {expense:{id,description,amount_cents,category}}
  DELETE /api/expenses/:id    -> HTTP 200 {deleted:boolean}
  GET /api/summary            -> HTTP 200 {count:int,total_cents:int,by_category:object}

Server/store.js exposes createStore(filePath). Its returned object implements
list(), create(body), delete(id). It MUST persist across a fresh createStore()
call with the same filePath. Store writes to the provided filePath only;
use require('node:fs') and no other dependencies. On invalid description or
amount_cents reject with Error.

Server/routes.js exposes createApp(store, processor), returning an Express app.
processor({expenses:store.list()}) returns the Python summary object. Use
require('express') only, express.json() and the exact response envelopes above.

Backend/logic.py defines transform(payload). It returns {count,total_cents,
by_category}, where by_category sums integer amount_cents by category, and
count is the expense count. Empty input returns count=0, total_cents=0 and
by_category={}. No external Python modules.

Client/App.jsx defines React function App, uses fetch for GET/POST/DELETE,
and displays a heading with PocketLedger, description and amount inputs,
Add expense button, expenses list, delete controls and a category summary.
No external UI libraries. CSS is responsive, valid and self-contained.
""".strip()

PUBLIC = [
    {"payload":{"expenses":[]},"expected":{"count":0,"total_cents":0,"by_category":{}}},
    {"payload":{"expenses":[{"amount_cents":1200,"category":"food"},{"amount_cents":499,"category":"travel"}]},
     "expected":{"count":2,"total_cents":1699,"by_category":{"food":1200,"travel":499}}},
    {"payload":{"expenses":[{"amount_cents":100,"category":"other"},{"amount_cents":250,"category":"other"}]},
     "expected":{"count":2,"total_cents":350,"by_category":{"other":350}}}
]


def holdout():
    """Never call while the model is selecting alternatives."""
    return [
        {"payload":{"expenses":[{"amount_cents":999,"category":"travel"}]},
         "expected":{"count":1,"total_cents":999,"by_category":{"travel":999}}},
        {"payload":{"expenses":[{"amount_cents":80,"category":"food"},{"amount_cents":20,"category":"food"},
                                {"amount_cents":300,"category":"other"}]},
         "expected":{"count":3,"total_cents":400,"by_category":{"food":100,"other":300}}},
        {"payload":{"expenses":[{"amount_cents":1,"category":"other"},{"amount_cents":2,"category":"travel"},
                                {"amount_cents":3,"category":"food"},{"amount_cents":4,"category":"other"}]},
         "expected":{"count":4,"total_cents":10,"by_category":{"other":5,"travel":2,"food":3}}}
    ]


def fingerprint():
    return hashlib.sha256(json.dumps({"spec":SPEC,"public":PUBLIC},
                                     sort_keys=True).encode()).hexdigest()


def prefix(role: str, *, mentor: bool=False) -> str:
    """Minimal signatures: executable bodies are Qwen-generated, not supplied."""
    if role not in ROLES:
        raise ValueError(role)
    marker={
        "logic":"# backend/logic.py; implement complete function body.\ndef transform(payload):\n",
        "store":"// server/store.js; code below implements durable storage.\nconst fs = require('node:fs');\nfunction createStore(filePath) {\n",
        "api":"// server/routes.js; implement ALL four endpoints.\nconst express = require('express');\nfunction createApp(store, processor) {\n",
        "ui":"// client/App.jsx; implement state, input form and fetch logic.\nconst React = require('react');\nfunction App() {\n",
        "css":"/* client/style.css; no imports, fonts or external URLs */\nbody {\n"
    }[role]
    common="\n".join(("# " if role=="logic" else "/* " if role=="css" else "// ")+
        line+(" */" if role=="css" else "") for line in SPEC.splitlines())+"\n"
    rules=""
    if mentor:
        from .mentor_patterns import load_bank, retrieve_patterns
        domain={"api":"express","store":"express","ui":"react","logic":"python","css":"react"}[role]
        matched=retrieve_patterns(SPEC+" "+marker,domain=domain,bank=load_bank())
        if matched:
            leader="# " if role=="logic" else "/* " if role=="css" else "// "
            trailer=" */" if role=="css" else ""
            rules="".join(leader+x["general_rule"]+trailer+"\n" for x in matched)
    return common+rules+marker
