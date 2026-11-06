"""Session031 contract: DevMetrics, a fresh full-stack developer dashboard.

A harder task than Session030's ShelfStock: two-resource analytics UI, six
Express routes, richer Python summary, invalid-input HTTP 400 handling, a
project filter, and a REQUIRED offline demo mode so the generated client can
run standalone in the published gallery. Field names, endpoints, routes and
the fixed demo dataset below are the complete public contract.
"""
from __future__ import annotations

import hashlib
import json
import re

NAME = "DevMetrics"
ROLES = ("logic", "store", "api", "ui", "css")

SPEC = """Build DevMetrics, a developer time-tracking dashboard. This task has
NEVER been used in previous experiments. Entries: id string, project nonempty
string, minutes positive integer, date 'YYYY-MM-DD' string, note string
possibly empty. Users log work entries, browse them with a project filter,
delete them, and read analytics. React frontend, Express routes, Python
summary, JSON on-disk storage.
 GET /api/health -> HTTP 200 {ok:true}
 GET /api/entries -> HTTP 200 {entries:[...]}
 POST /api/entries -> HTTP 201 {item:{id,project,minutes,date,note}};
   invalid input -> HTTP 400 {error:"..."}
 DELETE /api/entries/:id -> HTTP 200 {deleted:boolean}
 GET /api/projects -> HTTP 200 {projects:[distinct sorted project names]}
 GET /api/summary -> HTTP 200 processor({entries:store.list()}) directly.
 Store createStore(filePath) returns list(), create(body), delete(id),
 persists each mutation and must work before the file exists. Invalid
 project/minutes/date throws Error. Processor receives {entries:store.list()}.
 Python summarize(payload) returns total_minutes, by_project, by_day,
 active_projects and busiest_day (date with most minutes; ties -> earliest
 date; empty -> None). React App uses state, effects, fetch GET/POST/DELETE,
 a project filter, summary cards and a by-project breakdown. If any API
 request fails or the response is not ok, the UI must switch to OFFLINE DEMO
 MODE: show a visible badge containing the word offline, and operate fully on
 the built-in fixed demo dataset below (computed locally in JS):
   {project:'api-server', minutes:95, date:'2026-11-03', note:'routes'}
   {project:'mobile-ui', minutes:140, date:'2026-11-04', note:'screens'}
   {project:'docs', minutes:60, date:'2026-11-04', note:'guide'}
 In offline mode the list shows these three entries and the summary shows
 total minutes as the plain number 295. CSS responsive; no third-party UI
 packages, no imports of external assets, fonts or URLs.""".strip()

PUBLIC = [
    {"payload": {"entries": []},
     "expected": {"total_minutes": 0, "by_project": {}, "by_day": {},
                  "active_projects": 0, "busiest_day": None}},
    {"payload": {"entries": [
        {"project": "api-server", "minutes": 95, "date": "2026-11-03"},
        {"project": "mobile-ui", "minutes": 140, "date": "2026-11-04"},
        {"project": "docs", "minutes": 60, "date": "2026-11-04"}]},
     "expected": {"total_minutes": 295,
                  "by_project": {"api-server": 95, "mobile-ui": 140, "docs": 60},
                  "by_day": {"2026-11-03": 95, "2026-11-04": 200},
                  "active_projects": 3, "busiest_day": "2026-11-04"}},
    {"payload": {"entries": [
        {"project": "core", "minutes": 45, "date": "2026-11-01"},
        {"project": "core", "minutes": 30, "date": "2026-11-02"},
        {"project": "tests", "minutes": 25, "date": "2026-11-01"}]},
     "expected": {"total_minutes": 100,
                  "by_project": {"core": 75, "tests": 25},
                  "by_day": {"2026-11-01": 70, "2026-11-02": 30},
                  "active_projects": 2, "busiest_day": "2026-11-01"}},
]


def holdout():
    return [
        {"payload": {"entries": [
            {"project": "alpha", "minutes": 10, "date": "2026-10-01"}]},
         "expected": {"total_minutes": 10, "by_project": {"alpha": 10},
                      "by_day": {"2026-10-01": 10}, "active_projects": 1,
                      "busiest_day": "2026-10-01"}},
        {"payload": {"entries": [
            {"project": "x", "minutes": 5, "date": "2026-05-05"},
            {"project": "y", "minutes": 5, "date": "2026-05-05"},
            {"project": "z", "minutes": 3, "date": "2026-05-06"}]},
         "expected": {"total_minutes": 13, "by_project": {"x": 5, "y": 5, "z": 3},
                      "by_day": {"2026-05-05": 10, "2026-05-06": 3},
                      "active_projects": 3, "busiest_day": "2026-05-05"}},
        {"payload": {"entries": [
            {"project": "solo", "minutes": 7, "date": "2026-01-01"},
            {"project": "solo", "minutes": 2, "date": "2026-01-02"}]},
         "expected": {"total_minutes": 9, "by_project": {"solo": 9},
                      "by_day": {"2026-01-01": 7, "2026-01-02": 2},
                      "active_projects": 1, "busiest_day": "2026-01-01"}},
    ]


GOALS = {
    "logic": """Implement Python summarize(payload). Input is a dict whose
'entries' key is a list of entry dicts with keys project (string), minutes
(positive integer), date ('YYYY-MM-DD' string). Return a dict with EXACTLY
these keys: total_minutes (sum of all minutes), by_project (project name ->
summed minutes), by_day (date -> summed minutes), active_projects (count of
distinct project names), busiest_day (the date string with the highest total
minutes; on a tie choose the earliest date string; when there are no entries
return None). Empty input returns 0, {}, {}, 0, None. Only complete the
function body; no imports or extra function definitions.""",
    "store": """Implement Node createStore(filePath). Return an object with
list(), create(body), delete(id). Entries have id (string), project (nonempty
string), minutes (positive integer), date (string matching YYYY-MM-DD with
dashes), note (string, empty string when not provided). Save a JSON array to
disk after each mutation; if the file is missing treat it as empty. create
validates project, minutes and date and throws Error('Invalid entry') on any
violation, otherwise assigns a new unique string id, appends and returns the
entry. delete(id) returns true when an entry was removed, false otherwise. A
new createStore(filePath) must see earlier changes. Finish and close the
function, without redeclaring 'fs' or createStore.""",
    "api": """Implement Express createApp(store, processor). All routes inside
the factory; app.use(express.json()); GET /api/health returns {ok:true};
GET /api/entries returns {entries:store.list()}; POST /api/entries passes
req.body to store.create and returns HTTP 201 {item:created}; when store.create
throws, catch it and return HTTP 400 {error:'Invalid entry'}; DELETE
/api/entries/:id returns {deleted:store.delete(req.params.id)}; GET
/api/projects returns {projects: sorted distinct project names from
store.list()}; GET /api/summary returns processor({entries:store.list()})
directly. Return the app. Never call app.listen(). Don't redeclare
express/createApp.""",
    "ui": """Implement React function App with React.useState and
React.useEffect. Load GET /api/entries and GET /api/summary via fetch; treat a
failed request OR a response without res.ok as failure. On failure switch to
OFFLINE DEMO MODE: show a visible badge containing the word offline, and use
the fixed built-in demo entries [{project:'api-server',minutes:95,
date:'2026-11-03',note:'routes'},{project:'mobile-ui',minutes:140,
date:'2026-11-04',note:'screens'},{project:'docs',minutes:60,
date:'2026-11-04',note:'guide'}] with a JS summary computed exactly like the
Python summarize (total minutes 295, by_project, by_day, active_projects,
busiest_day). Show a DevMetrics heading, summary cards with total_minutes as a
plain number, a by-project breakdown, editable project, minutes, date and note
inputs, an Add button whose form event sends POST /api/entries with JSON then
refreshes, a project filter, a list of entries and Delete buttons that send
DELETE /api/entries/:id then refresh. Complete the function and module.exports;
don't redeclare React/App.""",
    "css": """Write clean, responsive CSS for a DevMetrics dashboard: dark
theme, cards for summary numbers, styled form inputs and buttons, list rows
with delete buttons, a badge style for the offline notice, and a mobile
friendly single-column layout. No external assets, imports, fonts or URLs;
close all braces.""",
}

# Public worked examples: contract-level documentation shown in generation
# prompts. They restate PUBLIC behavior only; SPEC/PUBLIC/GOALS (and therefore
# fingerprint()) are unchanged.
EXAMPLES = {
 "logic": """PUBLIC EXAMPLE (exact shapes):
summarize({"entries":[{"project":"api-server","minutes":95,"date":"2026-11-03"},
{"project":"docs","minutes":60,"date":"2026-11-03"}]})
returns
{"total_minutes":155,"by_project":{"api-server":95,"docs":60},
"by_day":{"2026-11-03":155},"active_projects":2,"busiest_day":"2026-11-03"}
Return ONE dict, never a tuple or separate values.""",
 "store": """PUBLIC EXAMPLE (exact behavior):
const s = createStore('store-data.json');
s.create({project:'api-server',minutes:95,date:'2026-11-03',note:'routes'})
returns {id:'1',project:'api-server',minutes:95,date:'2026-11-03',note:'routes'}
s.list() returns an array containing that entry.
A NEW createStore('store-data.json') still lists it (file persistence).
s.create({project:'',minutes:5,date:'2026-11-03'}) throws Error('Invalid entry').
create must return id as a STRING like '1', never the number 1.
Write ONLY to the filePath parameter; never hardcode any filename.
Use ONLY fs.readFileSync and fs.writeFileSync (never callback fs.writeFile).
Values you reassign later must be declared with let, never const.""",
 "api": """PUBLIC EXAMPLE (exact routes and envelopes):
GET /api/entries -> 200 {"entries":[]}
POST /api/entries with JSON body {"project":"api-server","minutes":95,
"date":"2026-11-03","note":"routes"} -> 201
{"item":{"id":"1","project":"api-server","minutes":95,"date":"2026-11-03",
"note":"routes"}}
POST /api/entries with body {"project":"","minutes":5,"date":"2026-11-03"}
-> 400 {"error":"Invalid entry"}
DELETE /api/entries/1 -> 200 {"deleted":true}
GET /api/projects -> 200 {"projects":["api-server"]}
GET /api/summary -> 200 and the body is exactly processor({entries:store.list()})
called directly inside the route; never redeclare processor.
Register handlers for ALL SIX endpoint paths above; never skip GET /api/entries.
Sorted distinct project names in JavaScript: Array.from(new Set(list)).sort().
End the module immediately after createApp's closing }.
NEVER write usage lines after the function: no const app = createApp(...),
no app.listen(...), no console.log after the function.""",
 "ui": """PUBLIC EXAMPLE (offline demo mode rendering):
badge with the word offline, then entry rows
api-server 95 min 2026-11-03, mobile-ui 140 min 2026-11-04,
docs 60 min 2026-11-04, then a summary with total minutes 295.
React hook lines look EXACTLY like this (note the full brackets):
const [entries, setEntries] = React.useState([]);
const [form, setForm] = React.useState({ project: '', minutes: '', date: '', note: '' });
React.useEffect(() => { load(); }, []);
Every opening bracket needs its closing bracket on the same hook line.
Write EXACTLY five React.useState lines: entries, form, filter, summary, offline.
NEVER add any other hook: no loading, error, refreshing, entryId, current, no sixth hook.
Keep the whole module under 100 lines and end it with module.exports = App;
Every JSX opening tag needs its matching closing tag before module.exports.""",
 "css": """PUBLIC EXAMPLE: style .badge, .cards, .card, .entries and form
controls; keep it responsive under 640px.""",
}

PREFIX = {
    "logic": "def summarize(payload):\n",
    "store": "const fs = require('node:fs');\nfunction createStore(filePath) {\n",
    "api": "const express = require('express');\nfunction createApp(store, processor) {\n",
    "ui": "const React = require('react');\nfunction App() {\n",
    "css": "body {\n",
}

FIELDS = ("id", "project", "minutes", "date", "note")
ENDPOINTS = ("GET /api/health", "GET /api/entries", "POST /api/entries",
             "DELETE /api/entries/:id", "GET /api/projects", "GET /api/summary")
DEMO_PROJECTS = ("api-server", "mobile-ui", "docs")


def prompt(role, error: str = "", previous: str = "",
            own_example: str = "", show_previous: bool = True) -> str:
    """Build a generation prompt.

    Allowed inputs ONLY: the public contract, the model's own previous attempt,
    public execution feedback, and (optionally) the model's OWN verified bytes
    from an earlier session — self-memory, never teacher- or human-written code.
    show_previous=False (seventh amendment) hides the full previous module
    while still quoting its failing lines, so the model regenerates from the
    contract instead of copying its own previous structure verbatim.
    """
    if role not in ROLES:
        raise ValueError(role)
    c = "#" if role == "logic" else "/*" if role == "css" else "//"
    end = " */" if role == "css" else ""

    def line(x):
        return f"{c} {x}{end}\n"

    def block(text):
        return "".join(line(x[:120]) for x in text.splitlines()[:34])

    text = line("NEW DEVMETRICS TASK. Generate only the completion under the final signature.")
    text += "".join(line(x) for x in GOALS[role].splitlines())
    text += "".join(line(x) for x in EXAMPLES[role].splitlines())
    text += line("FIELD NAMES (use exactly): " + ", ".join(FIELDS) + ".")
    if role in ("api", "ui"):
        text += line("ENDPOINTS (use exactly): " + "; ".join(ENDPOINTS) + ".")
    if own_example:
        text += line("YOUR OWN PREVIOUSLY VERIFIED WORKING CODE from a different")
        text += line("application you wrote (different field names and routes;")
        text += line("apply its structure only, never its old names):")
        text += block(own_example)
    if error:
        text += line("PUBLIC CHECK FEEDBACK: " + " ".join(str(error).split())[:300])
    if previous and show_previous:
        # Show the head (where early syntax bugs live) AND the tail of the
        # model's own previous attempt so no failure location is hidden.
        all_lines = previous.splitlines()
        head = [x[:110] for x in all_lines[:18]]
        tail = [x[:110] for x in all_lines[-10:]]
        if len(all_lines) <= 28:
            shown, gap = all_lines[:28], False
        else:
            shown, gap = head + tail, True
        if role == "logic":
            text += line("your previous attempt (it failed; write the corrected full body):")
            text += "".join(line(x) for x in shown)
        else:
            text += line("YOUR PREVIOUS ATTEMPT still fails; write a corrected full body:")
            text += "".join(line(x.replace("*/", "* /")) for x in shown)
        if gap:
            text += line("... (middle lines omitted) ...")
    if previous and error:
        # Sixth amendment: when execution feedback reports a line:column
        # position, quote the model's OWN lines around that exact position
        # so the failing spot is never hidden in the omitted middle of a
        # long module. Own bytes plus public execution feedback only.
        m = re.search(r":(\d+):(\d+)", str(error))
        if m:
            ln = int(m.group(1))
            own_lines = previous.splitlines()
            if 1 <= ln <= len(own_lines):
                lo, hi = max(1, ln - 3), min(len(own_lines), ln + 3)
                text += line("YOUR FAILING POSITION is line %d of your previous" % ln)
                text += line("attempt (reported by the evaluator). Your own lines")
                text += line("%d to %d around that position are:" % (lo, hi))
                for no in range(lo, hi + 1):
                    mark = ">>" if no == ln else "  "
                    text += line("%s%d: %s" % (mark, no,
                                  own_lines[no - 1].replace("*/", "* /")[:100]))
    return text + PREFIX[role]


def fingerprint():
    return hashlib.sha256(json.dumps(
        {"spec": SPEC, "public": PUBLIC, "goals": GOALS},
        sort_keys=True).encode()).hexdigest()
