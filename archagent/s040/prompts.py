"""Session 040 Track A-D prompt construction from the frozen v2 contracts.

Prompt laws inherited from Session 037/038A evidence:
  L-ANCHOR  the anchor sits INSIDE the target construct (first line of the
            required export) — never a bare import line (early-EOS).
  L-DEMO    demo-completeness: the demo shows every construct shape the task
            requires, in a DIFFERENT domain (greenhouse) from every task
            domain (aquarium/observatory/radiostation/...), so vocabulary
            copying is detectable and non-productive.
  L-BOUND   spec clauses stay <= 6.
  L-DIFF    explicit "adapt patterns, never copy domain words" instruction.
  L-EOS     near-empty generations are recorded and retried once with a
            forced-continuation anchor (handled by the driver).
  L-TRIM    prose tails after the construct are cut mechanically at brace
            balance (driver); balance is CHECKED, never auto-fixed.

Track deltas (the experiment):
  A  UNASSISTED  — contract facts (names, required export, spec bullets)
                   + anchor. NO concept, NO demo, NO checklist.
  B  CONTRACT-FIRST — concept + greenhouse demo + bounded spec + domain-diff
                   + mini-checklist + anchor (the 037/038A B-track recipe).
  C  EXECUTION-FEEDBACK REPAIR — B attempt 1, then <=3 full-context
                   regenerations with the evaluator's failing checks
                   (counterexamples) quoted back. Full regeneration, never
                   FIM (038A: FIM cannot rewrite).
  D  DECOMPOSITION (react-interaction + fullstack-integration only) — the
                   controller splits the artifact into sub-pieces (helper
                   logic, then UI / api layer, then component), each
                   generated with a B-style prompt, then assembled
                   deterministically (disclosed).

Everything here is teacher-authored trusted prompt text; the model's
generations are never fed back as prompt material (only evaluator verdicts).
"""

from __future__ import annotations

import hashlib

# --------------------------------------------------------------- anchors

def anchor_for(entry: dict) -> str:
    skill = entry["skill"]
    child = entry["entities"]["child"]
    if skill == "schema-relationship":
        return f"model {child} {{\n"
    if skill == "state-invariant":
        return f"export function canAdvance{child}(record, parent) {{\n"
    if skill == "api-get-filter":
        return ('import { db } from "@/lib/db";\n\n'
                "export async function GET(request: Request) {\n")
    if skill == "api-post-validation":
        return ('import { db } from "@/lib/db";\n\n'
                "export async function POST(request: Request) {\n")
    if skill == "react-interaction":
        return ("import { useState } from 'react';\n\n"
                f"export default function {child}List({{ data }}) {{\n")
    if skill == "fullstack-integration":
        return ("import { useEffect, useState } from 'react';\n\n"
                f"export default function {child}Manager() {{\n")
    raise ValueError(f"unknown skill {skill}")


def concept_for(entry: dict) -> str:
    skill = entry["skill"]
    child = entry["entities"]["child"]
    parent = entry["entities"]["parent"]
    if skill == "schema-relationship":
        return (f"A Prisma schema links a child model {child} to a parent model {parent} "
                "through a foreign-key relation. The relation attribute must declare "
                "what happens to children when the parent is deleted.")
    if skill == "state-invariant":
        return (f"A state invariant is a pure predicate canAdvance{child}(record, parent) "
                "that returns true exactly when the workflow allows the child record "
                "to advance to its next status. It reads the current status and the "
                "related parent, and it must never mutate anything.")
    if skill == "api-get-filter":
        return ("A Next.js GET route handler returns a JSON envelope with a list of "
                "records and a total. Query parameters filter the list; the total "
                "counts the FILTERED rows. The response shape must match the contract "
                "exactly.")
    if skill == "api-post-validation":
        return ("A Next.js POST route handler creates a record. It validates the body "
                "first (missing or invalid fields get 400), checks that referenced "
                "rows exist (404 when they do not) and rejects duplicates (409); only "
                "then does it persist and return 201 with the created record.")
    if skill == "react-interaction":
        return (f"A React list component receives rows through a data prop (no fetch). "
                "It renders every row, provides a labeled search input, a labeled "
                "status filter select and a clear button, applies the filters "
                "together, and shows an explicit empty state when nothing matches.")
    if skill == "fullstack-integration":
        return (f"A React manager component loads a list from an API route on mount, "
                "shows a create form, POSTs it, and on success updates the visible "
                "list and total without a full page reload. Failed creates show the "
                "error and keep the form values.")
    raise ValueError(skill)


# ------------------------------------------------- greenhouse demo library

DEMOS: dict[str, str] = {
    "schema-relationship": """// demo (different domain — a greenhouse app)
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = "file:./dev.db"
}

model Greenhouse {
  id      String   @id @default(cuid())
  sensors Sensor[]

  @@map("greenhouses")
}

model Sensor {
  id           String     @id @default(cuid())
  label        String
  reading      Int
  greenhouseId String?
  status       String     @default("calibrating")
  greenhouse   Greenhouse? @relation(fields: [greenhouseId], references: [id], onDelete: SetNull)

  @@map("sensors")
}""",
    "state-invariant": """// demo (different domain — a greenhouse app)
// Pure predicate: true exactly when the sensor may advance one status.
export function canAdvanceSensor(record, greenhouse) {
  if (record.status === "retired") {
    return false;
  }
  if (record.status === "calibrating") {
    return record.reading > 0 && greenhouse !== null;
  }
  if (record.status === "monitoring") {
    return record.reading >= 1 && record.reading <= 500;
  }
  return false;
}""",
    "api-get-filter": """// demo (different domain — a greenhouse app)
// Note: use the GLOBAL Response.json (no next/server import) and import db
// from "@/lib/db".
import { db } from "@/lib/db";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const search = params.get("search") ?? "";
  const status = params.get("status") ?? "";
  const rows = await db.sensor.findMany({
    where: {
      ...(search ? { label: { contains: search } } : {}),
      ...(status ? { status } : {}),
    },
    orderBy: { reading: "asc" },
  });
  const filtered = rows.filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (!status || row.status === status));
  return Response.json({ sensors: filtered, total: filtered.length });
}""",
    "api-post-validation": """// demo (different domain — a greenhouse app)
// Note: use the GLOBAL Response.json (no next/server import) and import db
// from "@/lib/db".
import { db } from "@/lib/db";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.label !== "string" || body.label.trim() === "") {
    return Response.json({ error: "label is required" }, { status: 400 });
  }
  const reading = Number(body.reading);
  if (!Number.isInteger(reading) || reading < 1 || reading > 500) {
    return Response.json({ error: "reading must be 1..500" }, { status: 400 });
  }
  if (body.greenhouseId) {
    const greenhouse = await db.greenhouse.findUnique({ where: { id: body.greenhouseId } });
    if (!greenhouse) {
      return Response.json({ error: "greenhouse not found" }, { status: 404 });
    }
  }
  const duplicate = await db.sensor.findFirst({ where: { label: body.label.trim() } });
  if (duplicate) {
    return Response.json({ error: "label already exists" }, { status: 409 });
  }
  const sensor = await db.sensor.create({
    data: {
      label: body.label.trim(),
      reading,
      ...(body.greenhouseId ? { greenhouseId: body.greenhouseId } : {}),
      status: "calibrating",
    },
  });
  return Response.json(sensor, { status: 201 });
}""",
    "react-interaction": """// demo (different domain — a greenhouse app)
import { useState } from 'react';

export default function SensorList({ data }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const rows = (data || []).filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (status === 'all' || row.status === status));
  return (
    <div>
      <label htmlFor="sensor-search">Search sensors</label>
      <input id="sensor-search" type="search" value={search}
             onChange={(event) => setSearch(event.target.value)} />
      <label htmlFor="sensor-status">Filter by status</label>
      <select id="sensor-status" value={status}
              onChange={(event) => setStatus(event.target.value)}>
        <option value="all">All statuses</option>
        <option value="calibrating">Calibrating</option>
        <option value="monitoring">Monitoring</option>
        <option value="retired">Retired</option>
      </select>
      <button type="button" onClick={() => { setSearch(''); setStatus('all'); }}>
        Clear filters
      </button>
      {rows.length === 0 ? (
        <p data-testid="empty-state">No sensors match your filters.</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id}>
              <strong>{row.label}</strong> — {row.reading} — {row.status}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}""",
    "fullstack-integration": """// demo (different domain — a greenhouse app)
import { useEffect, useState } from 'react';

const ROUTE = '/api/greenhouse-sensors';

export default function SensorManager() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [label, setLabel] = useState('');
  const [reading, setReading] = useState('1');
  const [error, setError] = useState('');

  const load = async () => {
    const response = await fetch(ROUTE);
    const data = await response.json();
    setRows(data.sensors || []);
    setTotal(data.total ?? 0);
  };

  useEffect(() => { load(); }, []);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    const response = await fetch(ROUTE, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ label, reading: Number(reading) }),
    });
    if (response.status === 201) {
      setLabel('');
      await load();
    } else {
      const data = await response.json().catch(() => ({}));
      setError(data.error || `Request failed (${response.status})`);
    }
  };

  return (
    <div>
      <h1>Sensor manager</h1>
      <form onSubmit={submit}>
        <label htmlFor="label">Label</label>
        <input id="label" value={label} onChange={(event) => setLabel(event.target.value)} />
        <label htmlFor="reading">Reading</label>
        <input id="reading" type="number" min="1" max="500" value={reading}
               onChange={(event) => setReading(event.target.value)} />
        <button type="submit">Create</button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      <p>Total: {total}</p>
      <ul>
        {rows.map((row) => (
          <li key={row.id}><strong>{row.label}</strong> — {row.reading} — {row.status}</li>
        ))}
      </ul>
    </div>
  );
}""",
}


def checklist_for(entry: dict) -> str:
    skill = entry["skill"]
    child = entry["entities"]["child"]
    fk = entry["entities"]["foreign_key"]
    amount = entry["fields"]["amount"]
    lo, hi = entry["fields"]["min_inclusive"], entry["fields"]["max_inclusive"]
    states = entry["workflow"]
    if skill == "schema-relationship":
        return (f"Checklist: model {child} exists; {fk} foreign key correct; "
                f"onDelete semantics correct; status String @default(\"{states[0]}\"); "
                f"{amount} Int; both models mapped.")
    if skill == "state-invariant":
        return (f"Checklist: export function canAdvance{child}; pure boolean return; "
                f"handles statuses {states}; returns false for unknown/terminal cases.")
    if skill == "api-get-filter":
        return ("Checklist: GET export; envelope with list and total; filters applied; "
                "total counts filtered rows; NextResponse.json used.")
    if skill == "api-post-validation":
        return (f"Checklist: POST export; 400 for bad/missing fields ({amount} integer "
                f"{lo}..{hi}); 404 for unknown relation; 409 duplicate; 201 created.")
    if skill == "react-interaction":
        return ("Checklist: default export component; uses the data prop; labeled search; "
                "labeled status select; clear button; empty state; no fixed widths.")
    if skill == "fullstack-integration":
        return ("Checklist: default export; loads list on mount; create form; POST on "
                "submit; 201 refreshes list and total; errors visible with form preserved.")
    raise ValueError(skill)


SPEC_NOTE = ("Adapt the demo's PATTERNS to this task's real names and domain — "
             "never copy the demo's domain words.")


def _spec_clauses(entry: dict) -> str:
    reqs = list(entry["requirements"])
    if len(reqs) > 6:
        reqs = reqs[:6]
    return "\n".join(f"- {r}" for r in reqs)


def _common(entry: dict) -> str:
    return (f"Task: {entry['user_story']}\n"
            f"Requirements:\n{_spec_clauses(entry)}\n")


# ------------------------------------------------------------- track A

def build_track_a(entry: dict) -> str:
    kind_word = {
        "schema-relationship": "Prisma schema",
        "state-invariant": "predicate function",
        "api-get-filter": "route handler",
        "api-post-validation": "route handler",
        "react-interaction": "React component",
        "fullstack-integration": "React component",
    }[entry["skill"]]
    parts = [
        _common(entry),
        f"Write the complete {kind_word} now. The first line is already written; continue from it:",
        anchor_for(entry),
    ]
    return "\n".join(parts)


# ------------------------------------------------------------- track B

def build_track_b(entry: dict) -> str:
    parts = [
        concept_for(entry),
        "",
        DEMOS[entry["skill"]],
        "",
        f"Now YOUR task (a different domain): {_common(entry)}",
        SPEC_NOTE,
        "",
        checklist_for(entry),
        "",
        "Write the complete construct now. The first line is already written; continue from it:",
        anchor_for(entry),
    ]
    return "\n".join(parts)


# ------------------------------------------------------------- track C

def build_track_c_repair(entry: dict, attempt: int, failing_checks: list[dict]) -> str:
    feedback_lines = []
    for check in failing_checks[:8]:
        name = check.get("name", "check")
        detail = str(check.get("detail", "")).strip()
        feedback_lines.append(f"- {name}" + (f": {detail}" if detail else ""))
    parts = [
        concept_for(entry),
        "",
        DEMOS[entry["skill"]],
        "",
        f"Now YOUR task (a different domain): {_common(entry)}",
        SPEC_NOTE,
        "",
        f"Your previous attempt had these VERIFIED problems (attempt {attempt}):",
        "\n".join(feedback_lines),
        "Fix exactly those problems; keep everything else that was correct.",
        "",
        checklist_for(entry),
        "",
        "Write the corrected complete construct now. The first line is already written; continue from it:",
        anchor_for(entry),
    ]
    return "\n".join(parts)


# ------------------------------------------------------------- track D

def decomposition_supported(entry: dict) -> bool:
    return entry["skill"] in ("react-interaction", "fullstack-integration")


def build_track_d_prompts(entry: dict) -> list[dict]:
    """Controller-decomposed sub-piece prompts; the driver assembles the parts."""
    skill = entry["skill"]
    child = entry["entities"]["child"]
    label = entry["fields"]["label"]
    amount = entry["fields"]["amount"]
    states = entry["workflow"]
    if skill == "react-interaction":
        helper = f"""// Sub-piece 1 of 2 (different domain — a greenhouse app)
// demo helper:
export function applySensorFilters(rows, search, status) {{
  return (rows || []).filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (status === 'all' || row.status === status));
}}

Now YOUR task (a different domain): write the filtering helper for {child} rows.
Requirements:
- export function filter{child}Rows(rows, search, status)
- rows have fields {label}, {amount}, status ('{states[0]}' | '{states[1]}' | '{states[2]}')
- search matches the {label} field case-insensitively
- status 'all' or empty means no status filtering
- return the filtered array; never mutate rows
The first line is already written; continue from it:
export function filter{child}Rows(rows, search, status) {{"""
        component = f"""// Sub-piece 2 of 2 (different domain — a greenhouse app)
// demo component USES a filtering helper exactly like yours:
export default function SensorList({{ data }}) {{
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const rows = applySensorFilters(data, search, status);
  return (
    <div>
      <label htmlFor="search">Search sensors</label>
      <input id="search" type="search" value={{search}} onChange={{(e) => setSearch(e.target.value)}} />
      <label htmlFor="status">Filter by status</label>
      <select id="status" value={{status}} onChange={{(e) => setStatus(e.target.value)}}>
        <option value="all">All</option>
        <option value="calibrating">Calibrating</option>
        <option value="monitoring">Monitoring</option>
      </select>
      <button type="button" onClick={{() => {{ setSearch(''); setStatus('all'); }}}}>Clear filters</button>
      {{rows.length === 0 ? <p data-testid="empty-state">No sensors match.</p> : (
        <ul>{{rows.map((row) => <li key={{row.id}}>{{row.label}} — {{row.status}}</li>)}}</ul>
      )}}
    </div>
  );
}}

Now YOUR task (a different domain): {_common(entry)}
Your helper filter{child}Rows(rows, search, status) is already written (import it from './helpers').
Requirements:
- default export component {child}List({{ data }})
- call filter{child}Rows for the visible rows
- labeled search input, labeled status select with options all/{states[0]}/{states[1]}/{states[2]}, clear button
- explicit empty state when no rows match
- render {label}, {amount} and status for each row
{SPEC_NOTE}
The first line is already written; continue from it:
export default function {child}List({{ data }}) {{"""
        return [
            {"name": f"filter{child}Rows", "prompt": helper, "max_tokens": 300,
             "anchor": f"export function filter{child}Rows(rows, search, status) {{"},
            {"name": f"{child}List", "prompt": component, "max_tokens": 800,
             "anchor": ("import {{ useState }} from 'react';\n\n"
                        f"export default function {child}List({{ data }}) {{\n")},
        ]
    if skill == "fullstack-integration":
        api = f"""// Sub-piece 1 of 2 (different domain — a greenhouse app)
// demo api layer:
const ROUTE = '/api/greenhouse-sensors';

export async function loadSensors() {{
  const response = await fetch(ROUTE);
  const data = await response.json();
  return {{ rows: data.sensors || [], total: data.total ?? 0 }};
}}

export async function createSensor(payload) {{
  const response = await fetch(ROUTE, {{
    method: 'POST',
    headers: {{ 'content-type': 'application/json' }},
    body: JSON.stringify(payload),
  }});
  return response;
}}

Now YOUR task (a different domain): write the api layer for {child}.
Requirements:
- export async function load{child}List() — GETs the route {entry['_route_path']} and returns {{ rows, total }} using the envelope key "{entry['_envelope_key']}"
- export async function create{child}(payload) — POSTs JSON and returns the Response
The first line is already written; continue from it:
export async function load{child}List() {{"""
        component = f"""// Sub-piece 2 of 2 (different domain — a greenhouse app)
// demo component USES an api layer exactly like yours:
export default function SensorManager() {{
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [label, setLabel] = useState('');
  const [error, setError] = useState('');

  const load = async () => {{
    const data = await loadSensors();
    setRows(data.rows);
    setTotal(data.total);
  }};
  useEffect(() => {{ load(); }}, []);

  const submit = async (event) => {{
    event.preventDefault();
    setError('');
    const response = await createSensor({{ label }});
    if (response.status === 201) {{ setLabel(''); await load(); }}
    else {{
      const data = await response.json().catch(() => ({{}}));
      setError(data.error || 'Request failed');
    }}
  }};
  return (
    <div>
      <form onSubmit={{submit}}>
        <label htmlFor="label">Label</label>
        <input id="label" value={{label}} onChange={{(e) => setLabel(e.target.value)}} />
        <button type="submit">Create</button>
      </form>
      {{error ? <p role="alert">{{error}}</p> : null}}
      <p>Total: {{total}}</p>
      <ul>{{rows.map((row) => <li key={{row.id}}>{{row.label}}</li>)}}</ul>
    </div>
  );
}}

Now YOUR task (a different domain): {_common(entry)}
Your api helpers load{child}List() and create{child}(payload) are already written (import from './api').
Requirements:
- default export component {child}Manager()
- load the list on mount via load{child}List()
- create form with labeled {entry['fields']['label']} input and {entry['fields']['amount']} number input
- submit calls create{child}; on 201 reload the list (visible rows and total update without page reload)
- on failure show the error (role=alert or visible text) and keep the form values
- display the total
{SPEC_NOTE}
The first line is already written; continue from it:
export default function {child}Manager() {{"""
        return [
            {"name": f"api-{child}", "prompt": api, "max_tokens": 350,
             "anchor": f"export async function load{child}List() {{"},
            {"name": f"{child}Manager", "prompt": component, "max_tokens": 900,
             "anchor": ("import {{ useEffect, useState }} from 'react';\n\n"
                        f"export default function {child}Manager() {{\n")},
        ]
    raise ValueError(f"track D does not support {skill}")


# ------------------------------------------------------------- utilities

def max_tokens_for(entry: dict) -> int:
    return {
        "schema-relationship": 400,
        "state-invariant": 250,
        "api-get-filter": 500,
        "api-post-validation": 650,
        "react-interaction": 800,
        "fullstack-integration": 900,
    }[entry["skill"]]


def seed_for(track: str, task_id: str) -> int:
    digest = hashlib.sha256(f"s040|{track}|{task_id}".encode()).hexdigest()
    return int(digest[:8], 16) % (2 ** 31)
