"""TaskFlow contract: the complete public specification given to Qwen.

TaskFlow is a project and task management application with ten required
features: create projects, add tasks, assign priorities, mark tasks
complete, edit tasks, delete tasks, filter by status, search, view project
progress, and persist data across restarts.

Every module Qwen writes is validated against this contract by the isolated
worker (archagent/worker.js + archagent/py_worker.py).  The contract is
frozen before any generation happens; public cases guide candidate
selection, holdout cases are evaluated only after candidates are frozen.

Authorship rules (mission section 5): prompts may contain the public
contract, the model's own previous attempts, public execution errors and
programming-concept explanations.  Teacher-authored target code never
enters the modules.
"""
from __future__ import annotations

import hashlib
import json

NAME = "TaskFlow"
VERSION = "taskflow-contract-v2-logic-simplified"
ROLES = ("logic", "store", "api", "ui", "css")

SPEC = """Build TaskFlow, a project and task management application.
Projects: id string, name non-empty string, createdAt 'YYYY-MM-DD' string.
Tasks: id string, projectId string, title non-empty string,
priority one of 'low','medium','high' (default 'medium'),
status one of 'todo','doing','done' (default 'todo'),
createdAt 'YYYY-MM-DD' string.
Users create projects, add tasks to a project, assign task priorities,
mark tasks complete (status 'done'), edit task title/priority/status,
delete tasks and projects, filter tasks by status, search tasks by title,
and view per-project progress. Data persists across restarts in a JSON
file. React frontend, Express backend, Python progress processor,
JSON on-disk storage. Invalid input must throw (store) or return
HTTP 400 (api). Deleting a project also deletes its tasks.""".strip()

LOGIC_SPEC = """Write ONE Python function summarize_project(payload).
payload = {"project": {...}, "tasks": [...]} where tasks belong to the
project. Return a dict with EXACTLY these keys:
  total: int, number of tasks
  done: int, number of tasks with status "done"
  remaining: int, total minus done
  percent: int, round(100 * done / total), 0 when total is 0
Rules: never mutate the payload; empty tasks -> total 0, done 0, remaining
0, percent 0. Output only the function, no imports needed. Start with
'def summarize_project(payload):'."""

STORE_SPEC = """Write ONE JavaScript module: a factory createStore(filePath)
that manages projects and tasks with JSON file persistence at filePath.
It returns an object with EXACTLY these methods:
  listProjects() -> array of project copies (empty array at start)
  createProject(body) -> new project {id, name, createdAt}
      body: {name}; name must be a non-empty string or throw Error
  updateProject(id, body) -> updated project; throw Error if id unknown
      or body.name invalid when present
  deleteProject(id) -> true; also deletes the project's tasks;
      throw Error if id unknown
  listTasks(filter) -> array of task copies; filter {projectId?, status?, q?}
      projectId: exact match; status: exact match; q: case-insensitive
      substring match on title; missing keys match everything
  createTask(body) -> new task
      body: {projectId, title, priority?, status?};
      throw Error if projectId unknown, title not a non-empty string,
      priority not in ['low','medium','high'], status not in
      ['todo','doing','done']; defaults priority 'medium', status 'todo'
  updateTask(id, body) -> updated task; partial updates; same validation;
      throw Error if id unknown
  deleteTask(id) -> true; throw Error if id unknown
Ids are unique strings like "p1","p2" and "t1","t2" (separate counters).
createdAt uses fixed dates '2026-11-07' for all records.
Persistence: after every mutation write the full state as JSON to filePath
as {"projects":[...],"tasks":[...]}; on construction, if the file exists,
load it; if not, start empty. The store must work when the file does not
exist yet. Use: const fs = require('node:fs');
Synchronous fs is allowed. End with: module.exports = createStore;
Start with 'function createStore(filePath) {'."""

API_SPEC = """Write ONE JavaScript module: a function
createApi(app, store, processor) that registers Express routes on app.
store is the TaskFlow store; processor(payload) returns the Python
summarize_project result (already bridged).
Routes (EXACT paths and shapes):
  GET /api/health -> 200 {ok: true}
  GET /api/projects -> 200 {projects: store.listProjects()}
  POST /api/projects -> 201 {project} from req.body; invalid -> 400 {error}
  PUT /api/projects/:id -> 200 {project}; unknown id -> 404 {error};
      invalid -> 400 {error}
  DELETE /api/projects/:id -> 200 {deleted: true}; unknown -> 404 {error}
  GET /api/tasks -> 200 {tasks} filtered by req.query (projectId, status, q)
  POST /api/tasks -> 201 {task}; invalid -> 400 {error}
  PUT /api/tasks/:id -> 200 {task}; unknown -> 404 {error}; invalid -> 400
  DELETE /api/tasks/:id -> 200 {deleted: true}; unknown -> 404 {error}
  GET /api/projects/:id/progress -> 200 with processor({project, tasks})
      where tasks are the project's tasks; unknown -> 404 {error}
Store methods throw Error on invalid input; catch it and answer 400 with
{error: message}. Unknown-id errors must answer 404 (check the message
for 'not found' or compare before mutating). JSON bodies via
app.use(express.json()) FIRST. No other middleware.
Use: const express = require('express') only if you must create a router;
prefer registering handlers directly on the given app.
End with: module.exports = createApi;
Start with 'function createApi(app, store, processor) {'."""

UI_SPEC = """Write ONE React application module: function App() for TaskFlow.
Available imports: react (useState, useEffect). A global fetch(url, opts)
exists. The backend serves the routes GET/POST/PUT/DELETE
/api/projects, /api/tasks (GET /api/tasks?projectId=&status=&q=),
GET /api/projects/:id/progress.
App requirements, all rendered at once:
  - a projects sidebar: each project name is a button; clicking selects it
  - an "Add project" form with an input and a submit button (POST then
    refresh the project list)
  - when a project is selected, show its task area:
    - progress display: a div with className "progress" showing
      "P% (D/T)" where P=percent, D=done, T=total (from /progress)
    - "Add task" form: title input, priority select (low/medium/high),
      submit button (POST /api/tasks with projectId)
    - filter buttons with classNames "filter-all", "filter-todo",
      "filter-doing", "filter-done"
    - a search input with className "search" (GET /api/tasks?projectId=
      &status=&q=)
    - task rows className "task-row": the title text, the priority as
      text, a button className "toggle" that marks the task done
      (PUT status "done", or back to "todo" when already done), a button
      className "edit" that prompts() for a new title and PUTs it, and a
      button className "delete" (DELETE)
  - after every mutation, refetch the task list and progress
OFFLINE DEMO MODE: if ANY fetch fails or res.ok is false, set a state
"offline" to true, show a div with className "offline-badge" containing
the word "offline", and continue operating on this built-in demo data:
  projects: [{id:"p1", name:"Website Redesign", createdAt:"2026-11-07"}]
  tasks: [{id:"t1", projectId:"p1", title:"Draft homepage",
           priority:"high", status:"done", createdAt:"2026-11-07"},
          {id:"t2", projectId:"p1", title:"Review colors",
           priority:"low", status:"todo", createdAt:"2026-11-07"}]
In offline mode the app renders the demo project, its progress "50% (1/2)"
in the .progress div, both task rows, and mutations update local state
only. NO alert(); NO window.location changes; NO external URLs.
Use EXACTLY these five useState hooks (no more):
  projects, selectedId, tasks, form, offline. Use exactly two useEffect.
Keep the module under 130 lines. End with: module.exports = App;
Start with 'function App() {'."""

CSS_SPEC = """Write ONE JavaScript module exporting a CSS string for TaskFlow.
const css = `...`; module.exports = css;
The string must contain rules for these class selectors (each at least
once): .app, .sidebar, .project-btn, .task-row, .priority-high,
.priority-medium, .priority-low, .progress, .progress-fill, .filter-all,
.filter-todo, .filter-doing, .filter-done, .search, .offline-badge,
.add-form. Also include exactly one @media (max-width: 720px) block that
changes the layout for small screens (for example making .app a single
column). Use plain CSS, no imports, no external fonts or URLs. The .app
rule must use display:flex. The .progress rule must have a background.
No CSS comments. Keep it under 60 lines total.
Start with 'const css = `'."""

# Code anchors: the deterministic first lines of each module (exact public
# contract signatures).  The prompt ends with the anchor so the frozen base
# model continues with code instead of prose (Session 031's measured
# lesson).  The anchor bytes are TRUSTED-SCAFFOLD; every byte after the
# anchor is model output.
# Public worked examples (the public test cases shown as exact shapes —
# the Session 031 measured lesson: concrete input->output examples anchor
# the frozen model far better than prose descriptions).
EXAMPLES = {
    "logic": """PUBLIC EXAMPLE (exact shapes):
summarize_project({"project": {"id": "p1", "name": "Website Redesign"},
"tasks": [{"priority": "high", "status": "done"},
{"priority": "low", "status": "todo"}]})
returns
{"total": 2, "done": 1, "remaining": 1, "percent": 50}
summarize_project({"project": {"id": "p1"}, "tasks": []})
returns
{"total": 0, "done": 0, "remaining": 0, "percent": 0}
total, done, remaining, percent are plain ints.""",
    "store": """PUBLIC EXAMPLE (exact behavior):
const s = createStore('db.json');
s.createProject({name: 'Alpha'}) returns
{id: 'p1', name: 'Alpha', createdAt: '2026-11-07'}  // id is a STRING
and ADDS it: s.listProjects() now returns that project in an array.
Every create/update/delete must MUTATE the state array AND persist:
fs.writeFileSync(filePath, JSON.stringify({projects, tasks})).
s.createTask({projectId: 'p1', title: 'First'}) returns
{id: 't1', projectId: 'p1', title: 'First', priority: 'medium',
status: 'todo', createdAt: '2026-11-07'}  // defaults applied
and ADDS it: s.listTasks({}) now contains it.
s.createTask({projectId: 'zz', title: 'X'}) throws Error.
s.updateTask('t1', {status: 'done'}) CHANGES the stored task:
a later s.listTasks({}) shows status 'done'.
A NEW createStore('db.json') still lists them (file persistence:
write after EVERY mutation, read on construction).
s.listTasks({q: 'first'}) matches title case-insensitively;
{projectId: 'p1'} matches that project's tasks only.
Separate counters: projects 'p1','p2'... tasks 't1','t2'...
createdAt is ALWAYS the string '2026-11-07', never a Date.
Values reassigned later must use let, never const.
Write ONLY to the filePath parameter; use fs.readFileSync and
fs.writeFileSync only.""",
    "api": """PUBLIC EXAMPLE (exact routes and envelopes):
GET /api/health -> 200 {"ok": true}
POST /api/projects {"name": "Alpha"} -> 201
{"project": {"id": "p1", "name": "Alpha", "createdAt": "2026-11-07"}}
POST /api/projects {"name": ""} -> 400 {"error": "..."}
PUT /api/tasks/t1 {"status": "done"} -> 200 {"task": {...}}
PUT /api/tasks/zz {"status": "done"} -> 404 {"error": "..."}
DELETE /api/tasks/t1 -> 200 {"deleted": true}
GET /api/tasks?projectId=p1&status=done&q=first -> 200 {"tasks": [...]}
GET /api/projects/p1/progress -> 200 {"total": 2, "done": 1, ...}
Every handler answers exactly once with the exact status code.""",
    "ui": """PUBLIC EXAMPLE (structure):
const [projects, setProjects] = React.useState([]);
const [selectedId, setSelectedId] = React.useState(null);
const [tasks, setTasks] = React.useState([]);
const [form, setForm] = React.useState({project: '', title: '', priority: 'medium'});
const [offline, setOffline] = React.useState(false);
React.useEffect(() => { /* fetch projects once */ }, []);
After a mutation: refetch the task list and progress.
In offline mode render the demo data and update local state only.""",
    "css": """PUBLIC EXAMPLE (shape):
const css = `
.app { display: flex; }
.sidebar { width: 240px; }
@media (max-width: 720px) { .app { flex-direction: column; } }
`;
module.exports = css;""",
}

ANCHOR = {
    "logic": "def summarize_project(payload):\n",
    "store": "const fs = require('node:fs');\nfunction createStore(filePath) {\n",
    "api": "const express = require('express');\nfunction createApi(app, store, processor) {\n",
    "ui": "const React = require('react');\nfunction App() {\n",
    "css": "const css = `\n",
}

# Short line-oriented contract summaries used to build comment prompts.
GOALS = {
    "logic": """TaskFlow progress processor (Python). payload is a dict:
payload["project"] is the project, payload["tasks"] is the task list.
Start with: tasks = payload["tasks"]. Return dict with EXACTLY four keys:
total (int, len(tasks)), done (int, count of status "done"), remaining
(int, total - done), percent (int, round(100 * done / total), and 0 when
total is 0). Never mutate the payload. Empty tasks -> total 0, done 0,
remaining 0, percent 0. The four values are plain ints, never dicts.""",
    "store": """TaskFlow storage module (Node.js). Factory createStore(filePath)
returns object with methods: listProjects, createProject(body),
updateProject(id, body), deleteProject(id), listTasks(filter),
createTask(body), updateTask(id, body), deleteTask(id).
Project: {id, name, createdAt}. Task: {id, projectId, title, priority,
status, createdAt}. Ids "p1","p2" and "t1","t2" (separate counters).
createdAt fixed "2026-11-07". Defaults: priority "medium", status "todo".
Valid: priority in low/medium/high, status in todo/doing/done, name and
title non-empty strings, projectId must exist. Invalid or unknown id
throws Error. deleteProject also deletes its tasks. listTasks filter
{projectId, status, q}: exact match, q case-insensitive substring of
title, missing keys match all. Return copies, never internal objects.
Persist after EVERY mutation: fs.writeFileSync(filePath,
JSON.stringify({projects, tasks})). On construction load the file if it
exists (fs.existsSync, readFileSync, JSON.parse), else start empty.""",
    "api": """TaskFlow Express API module. Register handlers on the given app.
First register app.use(express.json()). Routes exactly:
GET /api/health -> 200 {ok: true}
GET /api/projects -> 200 {projects: store.listProjects()}
POST /api/projects -> 201 {project} or 400 {error}
PUT /api/projects/:id -> 200 {project} or 404 {error} or 400 {error}
DELETE /api/projects/:id -> 200 {deleted: true} or 404 {error}
GET /api/tasks -> 200 {tasks} filter by req.query projectId, status, q
POST /api/tasks -> 201 {task} or 400 {error}
PUT /api/tasks/:id -> 200 {task} or 404 {error} or 400 {error}
DELETE /api/tasks/:id -> 200 {deleted: true} or 404 {error}
GET /api/projects/:id/progress -> 200 processor({project, tasks}) or 404.
Store throws Error on invalid input: catch and answer 400 with
{error: message}. Unknown id: answer 404 {error: message} (the store
message contains "not found"). req.params.id is a string. Use try/catch
in every handler that can throw. The processor argument is a function,
call it with the payload object.""",
    "ui": """TaskFlow React application (one component, function App).
Use React.useState and React.useEffect (the anchor requires React).
State: projects, selectedId, tasks, form, offline (five useState).
Two useEffect only. fetch is global; backend routes: GET/POST
/api/projects, GET/POST/PUT/DELETE /api/tasks (GET /api/tasks?projectId=
&status=&q=), GET /api/projects/:id/progress.
Render: sidebar with each project name as button className "project-btn";
add-project form className "add-form" (input + submit; POST then refetch
projects); when a project is selected show: div className "progress" with
"P% (D/T)" text from the progress route; add-task form className
"add-form" (title input, priority select low/medium/high, submit; POST
with projectId); filter buttons classNames "filter-all", "filter-todo",
"filter-doing", "filter-done"; search input className "search" (refetch
with q); task rows className "task-row" showing title text and priority
text, a button className "toggle" (PUT status done, or todo when already
done), a button className "edit" (prompt() for new title, PUT), a button
className "delete" (DELETE). After every mutation refetch tasks and
progress. Check res.ok before res.json().
OFFLINE DEMO MODE: when any fetch rejects or res.ok is false, set offline
true, show div className "offline-badge" with the word offline, and use
the built-in demo data: project {id "p1", name "Website Redesign"} and
tasks [{id "t1", title "Draft homepage", priority "high", status "done"},
{id "t2", title "Review colors", priority "low", status "todo"}] both
projectId "p1", createdAt "2026-11-07". In offline mode progress shows
"50% (1/2)" and mutations update local state only. No alert(), no
window.location, no external URLs.""",
    "css": """TaskFlow CSS string. The anchor opens a template literal:
complete it with plain CSS then close the backtick. Rules needed for
classes: .app (display flex), .sidebar, .project-btn, .task-row,
.priority-high, .priority-medium, .priority-low, .progress (with a
background), .progress-fill, .filter-all, .filter-todo, .filter-doing,
.filter-done, .search, .offline-badge, .add-form. Include exactly one
@media (max-width: 720px) block changing the layout (e.g. .app becomes
one column). No imports, no url(), no fonts, no comments.""",
}

STAGE_A_SPEC = """You are planning the TaskFlow application:
""" + SPEC + """

List the architecture as compact JSON with EXACTLY these keys:
  components: array of component names (strings)
  entities: array of entity names (strings)
  routes: array of "METHOD /path" strings
  state_transitions: array of "from -> to" strings for task status
  dependencies: array of library names
Output ONLY the JSON object, no prose. The object has already started; continue it:
{"""

# ---------------------------------------------------------------------------
# public test cases (guide candidate selection; never the holdout)
# ---------------------------------------------------------------------------

DEMO_PROJECT = {"id": "p1", "name": "Website Redesign", "createdAt": "2026-11-07"}
DEMO_TASKS = [
    {"id": "t1", "projectId": "p1", "title": "Draft homepage",
     "priority": "high", "status": "done", "createdAt": "2026-11-07"},
    {"id": "t2", "projectId": "p1", "title": "Review colors",
     "priority": "low", "status": "todo", "createdAt": "2026-11-07"},
]

LOGIC_PUBLIC = [
    {"payload": {"project": DEMO_PROJECT, "tasks": []},
     "expected": {"total": 0, "done": 0, "remaining": 0, "percent": 0}},
    {"payload": {"project": DEMO_PROJECT, "tasks": DEMO_TASKS},
     "expected": {"total": 2, "done": 1, "remaining": 1, "percent": 50}},
    {"payload": {"project": DEMO_PROJECT, "tasks": [
        {"priority": "medium", "status": "doing"},
        {"priority": "medium", "status": "done"},
        {"priority": "high", "status": "done"},
        {"priority": "low", "status": "todo"}]},
     "expected": {"total": 4, "done": 2, "remaining": 2, "percent": 50}},
]

LOGIC_HOLDOUT = [
    {"payload": {"project": DEMO_PROJECT, "tasks": [
        {"priority": "high", "status": "done"}] * 3 +
        [{"priority": "low", "status": "todo"}]},
     "expected": {"total": 4, "done": 3, "remaining": 1, "percent": 75}},
    {"payload": {"project": DEMO_PROJECT, "tasks": [
        {"priority": "medium", "status": "doing"},
        {"priority": "medium", "status": "doing"}]},
     "expected": {"total": 2, "done": 0, "remaining": 2, "percent": 0}},
]

# store checks are executed as a scripted scenario by the worker
STORE_SCENARIO_PUBLIC = [
    {"op": "listProjects", "expect": []},
    {"op": "createProject", "body": {"name": "Alpha"}, "expect":
        {"id": "p1", "name": "Alpha", "createdAt": "2026-11-07"}},
    {"op": "createProject", "body": {"name": "Beta"}, "expect":
        {"id": "p2", "name": "Beta", "createdAt": "2026-11-07"}},
    {"op": "createProject", "body": {"name": ""}, "expectError": True},
    {"op": "createTask", "body": {"projectId": "p1", "title": "First task"},
     "expect": {"id": "t1", "projectId": "p1", "title": "First task",
                "priority": "medium", "status": "todo",
                "createdAt": "2026-11-07"}},
    {"op": "createTask", "body": {"projectId": "p1", "title": "Second",
                                  "priority": "high"},
     "expect": {"id": "t2", "priority": "high"}},
    {"op": "createTask", "body": {"projectId": "zz", "title": "X"},
     "expectError": True},
    {"op": "createTask", "body": {"projectId": "p1", "title": ""},
     "expectError": True},
    {"op": "createTask", "body": {"projectId": "p1", "title": "Bad",
                                  "priority": "urgent"}, "expectError": True},
    {"op": "updateTask", "id": "t1", "body": {"status": "done"},
     "expect": {"id": "t1", "status": "done", "priority": "medium"}},
    {"op": "updateTask", "id": "t1", "body": {"title": "First task v2"},
     "expect": {"title": "First task v2", "status": "done"}},
    {"op": "updateTask", "id": "zz", "body": {}, "expectError": True},
    {"op": "listTasks", "filter": {"projectId": "p1"},
     "expectCount": 2},
    {"op": "listTasks", "filter": {"projectId": "p1", "status": "done"},
     "expectCount": 1},
    {"op": "createTask", "body": {"projectId": "p2", "title": "Other task"},
     "expect": {"id": "t3"}},
    {"op": "listTasks", "filter": {"q": "task"}, "expectCount": 2},
    {"op": "listTasks", "filter": {"q": "FIRST"}, "expectCount": 1},
    {"op": "deleteTask", "id": "t2", "expect": True},
    {"op": "deleteTask", "id": "t2", "expectError": True},
    {"op": "updateProject", "id": "p1", "body": {"name": "Alpha v2"},
     "expect": {"id": "p1", "name": "Alpha v2"}},
    {"op": "deleteProject", "id": "p2", "expect": True},
    {"op": "listTasks", "filter": {"projectId": "p2"}, "expectCount": 0},
    {"op": "reload"},
    {"op": "listProjects", "expectCount": 1},
    {"op": "listTasks", "filter": {}, "expectCount": 1},
    {"op": "persistedShape"},
]

STORE_SCENARIO_HOLDOUT = [
    {"op": "createProject", "body": {"name": "Gamma"}, "expect":
        {"id": "p1", "name": "Gamma"}},
    {"op": "createTask", "body": {"projectId": "p1", "title": "Search me",
                                  "priority": "low", "status": "doing"},
     "expect": {"id": "t1", "status": "doing"}},
    {"op": "createTask", "body": {"projectId": "p1", "title": "Another"},
     "expect": {"id": "t2", "priority": "medium"}},
    {"op": "updateTask", "id": "t2", "body": {"priority": "high",
                                              "status": "done"},
     "expect": {"priority": "high", "status": "done"}},
    {"op": "updateTask", "id": "t1", "body": {"status": "nope"},
     "expectError": True},
    {"op": "listTasks", "filter": {"projectId": "p1", "status": "doing"},
     "expectCount": 1},
    {"op": "listTasks", "filter": {"q": "search"}, "expectCount": 1},
    {"op": "deleteProject", "id": "p1", "expect": True},
    {"op": "reload"},
    {"op": "listProjects", "expect": []},
    {"op": "listTasks", "filter": {}, "expectCount": 0},
]

API_CHECKS_PUBLIC = [
    {"name": "health", "method": "get", "path": "/api/health",
     "expect_status": 200, "expect_body": {"ok": True}},
    {"name": "post_project", "method": "post", "path": "/api/projects",
     "body": {"name": "Alpha"}, "expect_status": 201,
     "expect_body_contains": {"project": {"id": "p1", "name": "Alpha"}}},
    {"name": "post_project_invalid", "method": "post", "path": "/api/projects",
     "body": {"name": ""}, "expect_status": 400,
     "expect_body_contains": {"error": None}},
    {"name": "get_projects", "method": "get", "path": "/api/projects",
     "expect_status": 200, "expect_count": ("projects", 1)},
    {"name": "post_task", "method": "post", "path": "/api/tasks",
     "body": {"projectId": "p1", "title": "First", "priority": "high"},
     "expect_status": 201,
     "expect_body_contains": {"task": {"id": "t1", "priority": "high",
                                       "status": "todo"}}},
    {"name": "post_task_invalid", "method": "post", "path": "/api/tasks",
     "body": {"projectId": "p1", "title": ""}, "expect_status": 400},
    {"name": "put_task", "method": "put", "path": "/api/tasks/t1",
     "body": {"status": "done"}, "expect_status": 200,
     "expect_body_contains": {"task": {"status": "done"}}},
    {"name": "put_task_404", "method": "put", "path": "/api/tasks/zz",
     "body": {"status": "done"}, "expect_status": 404},
    {"name": "get_tasks_filter", "method": "get",
     "path": "/api/tasks?projectId=p1&status=done", "expect_status": 200,
     "expect_count": ("tasks", 1)},
    {"name": "get_tasks_search", "method": "get",
     "path": "/api/tasks?q=fir", "expect_status": 200,
     "expect_count": ("tasks", 1)},
    {"name": "delete_task", "method": "delete", "path": "/api/tasks/t1",
     "expect_status": 200, "expect_body": {"deleted": True}},
    {"name": "delete_task_404", "method": "delete", "path": "/api/tasks/t1",
     "expect_status": 404},
    {"name": "progress", "method": "get",
     "path": "/api/projects/p1/progress", "expect_status": 200,
     "expect_body_contains": {"percent": 0, "total": 0}},
    {"name": "delete_project", "method": "delete",
     "path": "/api/projects/p1", "expect_status": 200,
     "expect_body": {"deleted": True}},
    {"name": "progress_404", "method": "get",
     "path": "/api/projects/p1/progress", "expect_status": 404},
]

API_CHECKS_HOLDOUT = [
    {"name": "post_two_projects", "method": "post", "path": "/api/projects",
     "body": {"name": "One"}, "expect_status": 201},
    {"name": "post_project_two", "method": "post", "path": "/api/projects",
     "body": {"name": "Two"}, "expect_status": 201},
    {"name": "post_task_p2", "method": "post", "path": "/api/tasks",
     "body": {"projectId": "p2", "title": "Task in two"},
     "expect_status": 201,
     "expect_body_contains": {"task": {"priority": "medium"}}},
    {"name": "put_project", "method": "put", "path": "/api/projects/p1",
     "body": {"name": "One v2"}, "expect_status": 200,
     "expect_body_contains": {"project": {"name": "One v2"}}},
    {"name": "put_project_404", "method": "put", "path": "/api/projects/zz",
     "body": {"name": "X"}, "expect_status": 404},
    {"name": "delete_project_cascade", "method": "delete",
     "path": "/api/projects/p2", "expect_status": 200},
    {"name": "get_tasks_after_cascade", "method": "get",
     "path": "/api/tasks?projectId=p2", "expect_status": 200,
     "expect_count": ("tasks", 0)},
    {"name": "progress_404_after_delete", "method": "get",
     "path": "/api/projects/p2/progress", "expect_status": 404},
]

STAGE_A_REFERENCE = {
    "components": {"project list", "task list", "add project form",
                   "add task form", "filter controls", "search input",
                   "progress display"},
    "entities": {"project", "task"},
    "routes": {"GET /api/projects", "POST /api/projects",
               "PUT /api/projects/:id", "DELETE /api/projects/:id",
               "GET /api/tasks", "POST /api/tasks", "PUT /api/tasks/:id",
               "DELETE /api/tasks/:id", "GET /api/health",
               "GET /api/projects/:id/progress"},
    "state_transitions": {"todo -> doing", "doing -> done", "todo -> done"},
    "dependencies": {"express", "react"},
}


def fingerprint() -> str:
    """Stable fingerprint of the frozen contract."""
    blob = json.dumps({
        "name": NAME, "version": VERSION, "spec": SPEC,
        "logic": LOGIC_SPEC, "store": STORE_SPEC, "api": API_SPEC,
        "ui": UI_SPEC, "css": CSS_SPEC,
        "anchor": ANCHOR, "goals": GOALS,
        "logic_public": LOGIC_PUBLIC, "logic_holdout": LOGIC_HOLDOUT,
        "store_public": STORE_SCENARIO_PUBLIC,
        "store_holdout": STORE_SCENARIO_HOLDOUT,
        "api_public": API_CHECKS_PUBLIC, "api_holdout": API_CHECKS_HOLDOUT,
        "stage_a": STAGE_A_SPEC,
    }, sort_keys=True).encode("utf8")
    return hashlib.sha256(blob).hexdigest()


def holdout_digest() -> str:
    blob = json.dumps({
        "logic": LOGIC_HOLDOUT, "store": STORE_SCENARIO_HOLDOUT,
        "api": API_CHECKS_HOLDOUT,
    }, sort_keys=True).encode("utf8")
    return hashlib.sha256(blob).hexdigest()[:16]


def commentize(role: str, text: str, width: int = 108) -> str:
    """Wrap text as role-appropriate comment lines (Session 031 format)."""
    c = "#" if role == "logic" else "//"
    out = []
    for raw in text.splitlines():
        line = raw.rstrip()
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            if cut <= 0:
                cut = width
            out.append(f"{c} {line[:cut]}")
            line = line[cut:].lstrip()
        out.append(f"{c} {line}" if line else c)
    return "\n".join(out) + "\n"


def prompt(role: str, *, docs: str = "", feedback: str = "",
           previous_excerpt: str = "", self_note: str = "",
           concept: str = "") -> str:
    """Generation prompt: comment contract (+docs/feedback) ending with the
    code anchor so the frozen base model continues with code."""
    if role == "stage_a":
        return STAGE_A_SPEC
    parts = [commentize(role, f"NEW {NAME} TASK. Complete the code after the"
                              " final signature. No prose.")]
    parts.append(commentize(role, GOALS[role]))
    parts.append(commentize(role, EXAMPLES[role]))
    if docs:
        parts.append(docs)
    if feedback:
        parts.append(commentize(role, "PUBLIC CHECK FEEDBACK: " + feedback))
    if concept:
        parts.append(commentize(role, "PROGRAMMING CONCEPT (no code): "
                                    + concept))
    if self_note:
        parts.append(commentize(role, self_note))
    if previous_excerpt:
        parts.append(commentize(
            role, "YOUR PREVIOUS ATTEMPT still fails; write a corrected"
                  " full body. Your previous lines:"))
        parts.append(previous_excerpt)
    return "".join(parts) + "\n" + ANCHOR[role]
