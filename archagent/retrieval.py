"""Controlled documentation retrieval for the archagent harness.

Local, pinned documentation snapshots (TRUSTED-SCAFFOLD: authored by the
harness, not by the model, and never containing target TaskFlow code).
They explain library concepts only.  The experiment compares:
  (1) no retrieval,
  (2) relevant documentation retrieval,
  (3) documentation retrieval + execution feedback (repair loop).
Cost accounting records the extra prompt tokens each mode adds.
"""
from __future__ import annotations

DOCS: dict[str, str] = {
    "express": """Express routing reference (pinned concepts, v4):
- app.get(path, handler), app.post(path, handler), app.put(path, handler),
  app.delete(path, handler) register route handlers on an existing app.
- Path parameters: '/api/tasks/:id' -> req.params.id is the string after
  /api/tasks/. Different routes can share the same parameter name.
- Query parameters: '/api/tasks?projectId=p1&status=done' -> req.query is
  an object like {projectId: 'p1', status: 'done'}. Values are strings.
  Missing keys are undefined.
- Request body: after app.use(express.json()), req.body is the parsed JSON
  object of POST/PUT requests with a JSON content type.
- Responses: res.status(code).json(obj). 201 for created, 200 for success,
  400 for invalid input, 404 for a missing resource.
- Handlers receive (req, res). A handler must answer exactly once.
- Synchronous throws inside a handler crash the request; wrap risky calls
  in try/catch and answer 400 or 404 with res.status(...).json({error: ...}).
- Register middleware BEFORE routes that need it.""",
    "react": """React function component reference (pinned concepts, v18):
- function App() { ... } returns JSX describing the whole screen.
- const [value, setValue] = useState(initial) adds state. setValue(next)
  schedules a re-render with the new value. State persists across renders.
- useEffect(() => { ... return cleanup; }, [deps]) runs AFTER render. Empty
  deps [] run once on mount. deps like [selectedId] re-run when the value
  changes. Fetch data inside useEffect, not during render.
- Conditional rendering: {cond && <div>...</div>} renders only when cond.
- Lists: {items.map(item => <div key={item.id}>{item.title}</div>])} needs
  a stable key per element.
- Forms: <form onSubmit={e => {e.preventDefault(); ...}}>; read inputs via
  controlled state value={form.title} onChange={e => setForm({...form,
  title: e.target.value})}.
- Never call setState synchronously during render; do it in handlers or
  effects.
- After a mutation (POST/PUT/DELETE succeeded), fetch the list again to
  refresh what the user sees.""",
    "fetch": """fetch reference (pinned concepts):
- await fetch(url) performs GET. await fetch(url, {method: 'POST', headers:
  {'Content-Type': 'application/json'}, body: JSON.stringify(data)}) sends
  JSON. PUT and DELETE follow the same shape with their method string.
- The promise REJECTS only on network failure; an HTTP error status (400,
  404) still resolves. Always check (await res).ok or res.status before
  using res.json().
- await res.json() parses the response body. Combine: const res = await
  fetch(url); if (!res.ok) throw Error('request failed'); const data =
  await res.json();
- Query strings are part of the url: '/api/tasks?projectId=' + id +
  '&status=' + status. Encode search text with encodeURIComponent(q).""",
    "fs": """Node fs reference (pinned concepts):
- const fs = require('node:fs') imports the filesystem module.
- fs.existsSync(path) -> boolean.
- fs.readFileSync(path, 'utf8') -> file contents string (throws if the
  file does not exist). JSON.parse(text) parses it.
- fs.writeFileSync(path, text) creates or replaces the file. Persist with
  fs.writeFileSync(filePath, JSON.stringify(state)).
- Wrap the initial load in if (fs.existsSync(filePath)) { ... } else { ... }
  so a fresh install without a data file starts empty instead of crashing.""",
    "js": """JavaScript reference (pinned concepts):
- const binds a name that cannot be reassigned. If a variable must change,
  declare it with let. Reassigning a const throws TypeError.
- Array.filter(fn) returns a new array of matching items; it does not
  modify the original.
- String.includes(sub) is exact-case; convert both sides with .toLowerCase()
  for case-insensitive substring search.
- Array.find(fn) returns the first match or undefined.
- Copy objects when returning them: {...item} makes a shallow copy so
  callers cannot mutate internal state.
- typeof x === 'string' checks the type; !x is true for '', null,
  undefined.""",
}

ROLE_DOCS = {
    "store": ("fs", "js"),
    "api": ("express", "js"),
    "ui": ("react", "fetch"),
    "logic": (),
    "css": (),
}


def doc_block(role: str) -> str:
    """Documentation block for a role's prompt (condition 2/3)."""
    keys = ROLE_DOCS.get(role, ())
    if not keys:
        return ""
    parts = []
    for k in keys:
        parts.append(f"/* Reference: {k} */\n" + DOCS[k])
    return "\n\n".join(parts) + "\n\n"


def doc_token_estimate(role: str) -> int:
    """Rough token estimate (~4 chars/token) for cost accounting."""
    return len(doc_block(role)) // 4
