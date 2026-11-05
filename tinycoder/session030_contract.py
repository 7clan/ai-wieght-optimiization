"""Fresh ShelfStock contract for transfer from observed PocketLedger corrections."""
from __future__ import annotations

import hashlib
import json

NAME="ShelfStock"
ROLES=("logic","store","api","ui","css")
SPEC="""Build ShelfStock, a small inventory app. This task has NEVER been used in
previous experiments. Records: id string, name nonempty string, units positive
integer, section one of pantry, tools, other. Users add inventory entries,
browse and delete them, and view totals by section. React frontend, Express
routes, Python summary, JSON on-disk storage.
 GET /api/items -> HTTP 200 {items:[...]}
 POST /api/items -> HTTP 201 {item:{id,name,units,section}}
 DELETE /api/items/:id -> HTTP 200 {deleted:boolean}
 GET /api/summary -> HTTP 200 {count,total_units,by_section}
 Store createStore(filePath) returns list(), create(body), delete(id), persists
 each mutation and must work before file exists. Invalid name/units throws Error.
 Processor receives {items:store.list()}. Python transform(payload) returns
 count, total_units, by_section grouped across every item, including empty.
 React App uses state, effects, fetch GET/POST/DELETE, inputs and category
 summary. CSS responsive; no third-party UI packages.""".strip()

PUBLIC=[
 {"payload":{"items":[]},"expected":{"count":0,"total_units":0,"by_section":{}}},
 {"payload":{"items":[{"units":7,"section":"pantry"},{"units":4,"section":"tools"}]},
  "expected":{"count":2,"total_units":11,"by_section":{"pantry":7,"tools":4}}},
 {"payload":{"items":[{"units":12,"section":"other"},{"units":5,"section":"other"}]},
  "expected":{"count":2,"total_units":17,"by_section":{"other":17}}}
]

def holdout():
    return [
      {"payload":{"items":[{"units":9,"section":"pantry"}]},
       "expected":{"count":1,"total_units":9,"by_section":{"pantry":9}}},
      {"payload":{"items":[{"units":2,"section":"tools"},{"units":8,"section":"pantry"},
                          {"units":3,"section":"tools"},{"units":1,"section":"other"}]},
       "expected":{"count":4,"total_units":14,
                   "by_section":{"tools":5,"pantry":8,"other":1}}},
      {"payload":{"items":[{"units":37,"section":"pantry"},{"units":1,"section":"tools"},
                          {"units":2,"section":"tools"}]},
       "expected":{"count":3,"total_units":40,
                   "by_section":{"pantry":37,"tools":3}}}
    ]

GOALS={
 "logic":"""Implement Python transform(payload). Input is a dict whose 'items'
key is a list of dicts. Output {count,total_units,by_section} with count of
items, sum of all units, and section subtotals. Empty input returns 0,0,{}.
Only complete the function body, no imports or extra function definitions.""",
 "store":"""Implement Node createStore(filePath). Return object with list(),
create(body), delete(id). Save a JSON list to disk after each mutation;
if the file is missing treat it as empty. Create validates nonempty 'name'
and positive integer 'units', returns an object with generated string 'id',
name,units,section. Delete returns boolean. A new createStore(filePath)
must see earlier changes. Finish and close the function, without redeclaring
'fs' or createStore.""",
 "api":"""Implement Express createApp(store,processor). All routes inside
factory; app.use(express.json()); GET /api/items returns {items:store.list()};
POST /api/items returns HTTP 201 {item:store.create(req.body)};
DELETE /api/items/:id returns {deleted:store.delete(req.params.id)};
GET /api/summary returns processor({items:store.list()}) directly.
Return the app. Never call app.listen(). Don't redeclare express/createApp.""",
 "ui":"""Implement React function App with React.useState and React.useEffect.
Load GET /api/items and GET /api/summary via fetch. Show ShelfStock heading,
editable name and units inputs and section dropdown. Form event sends POST
/api/items with JSON then refreshes. Render list of inventory items and Delete
buttons that send DELETE /api/items/:id then refresh. Show summary counts by
section. Complete function and module.exports; don't redeclare React/App.""",
 "css":"""Write clean, responsive CSS for a ShelfStock inventory dashboard.
No external assets, imports, fonts or URLs; close all braces."""
}

PREFIX={
 "logic":"def transform(payload):\n",
 "store":"const fs = require('node:fs');\nfunction createStore(filePath) {\n",
 "api":"const express = require('express');\nfunction createApp(store, processor) {\n",
 "ui":"const React = require('react');\nfunction App() {\n",
 "css":"body {\n"
}

def prompt(role,teacher:str|None=None,error:str="")->str:
    if role not in ROLES:raise ValueError(role)
    c="#" if role=="logic" else "/*" if role=="css" else "//"
    end=" */" if role=="css" else ""
    def line(x):return f"{c} {x}{end}\n"
    text=line("NEW SHELFSTOCK TASK. Generate only completion under the final signature.")
    text+="".join(line(x) for x in GOALS[role].splitlines())
    if teacher:
        text+=line("TEACHER'S CORRECTED WORKING CODE from DIFFERENT PocketLedger application:")
        # A full worked example is retrieval memory, NOT a target solution.
        text+=teacher+"\n"+line("Apply the same structural pattern to SHELFSTOCK fields/routes. Do not copy the old names.")
    if error:
        text+=line("PUBLIC CHECK FEEDBACK: "+" ".join(error.split())[:200])
    return text+PREFIX[role]

def fingerprint():
    return hashlib.sha256(json.dumps({"spec":SPEC,"public":PUBLIC,"goals":GOALS},
                                     sort_keys=True).encode()).hexdigest()
