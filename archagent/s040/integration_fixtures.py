"""Trusted Session-040 fullstack-integration fixtures derived from frozen v2 contracts.

Teacher-authored trusted material only: the Prisma schema/reseed fixtures
are reused from the Session-039 route evaluator (same frozen rows), plus a
TRUSTED reference API route implementing the frozen POST/GET semantics
(201 create, 400 blank/invalid field, 404 unknown relation, 409 duplicate
title, GET list envelope with total). The candidate supplies only the React
form/list component; its ``fetch`` calls are routed in-process to the
trusted reference route backed by the real seeded SQLite database, so the
evaluator measures genuine frontend->API->database integration without a
network stack. Nothing here reads, generates or executes model output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from archagent.s039 import route_fixtures, scenarios

INTEGRATION_SKILL = "fullstack-integration"
ROUTE_RE = re.compile(r"/api/[a-z0-9-]+")

ERROR_TEXT_RE = r"(error|invalid|fail|not found|does not exist|already exist|duplicate)"
TOTAL_TEXT_RE = r"(total|count)"


def integration_contract(repo: Path, split: str, task_id: str) -> dict:
    suite = scenarios.load_split(repo, split, suite_version=2)
    entries = [task for task in suite["tasks"] if task["id"] == task_id]
    if len(entries) != 1 or entries[0]["skill"] != INTEGRATION_SKILL:
        raise ValueError("Expected one frozen fullstack-integration task in train/dev")
    entry = entries[0]
    domain = entry["domain"]
    # The route path/envelope are stated by the sibling GET contract of the
    # same domain; the integration contract references "the GET/POST route".
    get_entry = next(task for task in suite["tasks"]
                     if task["id"] == f"{domain}:api-get-filter")
    get_requirements = " ".join(get_entry["requirements"])
    routes = sorted(set(ROUTE_RE.findall(get_requirements)))
    envelopes = sorted(set(route_fixtures.ENVELOPE_RE.findall(get_requirements)))
    if len(routes) != 1 or len(envelopes) != 1:
        raise ValueError(f"Domain {domain} GET contract lacks exactly one route/envelope")
    return {
        "task_id": task_id,
        "domain": domain,
        "skill": INTEGRATION_SKILL,
        "route_path": routes[0],
        "envelope_key": envelopes[0],
        "entities": {
            "parent_client": entry["entities"]["parent"].lower(),
            "child_client": entry["entities"]["child"].lower(),
            "foreign_key": entry["entities"]["foreign_key"],
            "foreign_key_optional": entry["entities"]["foreign_key_mode"] == "optional",
        },
        "fields": dict(entry["fields"]),
        "workflow": list(entry["workflow"]),
        "requirements": list(entry["requirements"]),
    }


def reference_route_mjs(spec: dict, *, client_import: str) -> str:
    """Trusted reference route implementing the frozen POST/GET semantics."""
    child = spec["entities"]["child_client"]
    parent = spec["entities"]["parent_client"]
    fk = spec["entities"]["foreign_key"]
    label = spec["fields"]["label"]
    amount = spec["fields"]["amount"]
    lo, hi = spec["fields"]["min_inclusive"], spec["fields"]["max_inclusive"]
    route_path = spec["route_path"]
    envelope = spec["envelope_key"]
    initial_status = spec["workflow"][0]
    return f"""// TRUSTED Session-040 fixture — AUTHORED_REFERENCE_ROUTE_NOT_QWEN_CODE
// Implements the frozen {spec['task_id']} contract semantics for POST create
// (400/404/409/201) and GET list ({{ {envelope}: [...], total }}).
import {{ db }} from "./lib/db.ts";

const jsonErr = (status, code, message) => new Response(
  JSON.stringify({{ error: code, message }}), {{ status }});

export async function GET() {{
  const rows = await db.{child}.findMany({{ orderBy: {{ id: "asc" }} }});
  return Response.json({{ {envelope}: rows, total: rows.length }});
}}

export async function POST(request) {{
  let body;
  try {{
    body = await request.json();
  }} catch {{
    return jsonErr(400, "invalid-json", "Request body must be valid JSON.");
  }}
  const title = typeof body.{label} === "string" ? body.{label}.trim() : "";
  if (!title) {{
    return jsonErr(400, "missing-{label}", "Field {label} is required.");
  }}
  const value = Number(body.{amount});
  if (!Number.isInteger(value) || value < {lo} || value > {hi}) {{
    return jsonErr(400, "invalid-{amount}", "Field {amount} must be an integer between {lo} and {hi}.");
  }}
  const fkValue = body.{fk};
  if (fkValue !== undefined && fkValue !== null && fkValue !== "") {{
    if (typeof fkValue !== "string") {{
      return jsonErr(400, "invalid-{fk}", "Field {fk} must be a string id.");
    }}
    const related = await db.{parent}.findUnique({{ where: {{ id: fkValue }} }});
    if (!related) {{
      return jsonErr(404, "unknown-{fk}", "Related {parent} was not found.");
    }}
  }}
  const duplicate = await db.{child}.findFirst({{ where: {{ {label}: title }} }});
  if (duplicate) {{
    return jsonErr(409, "duplicate-{label}", "A record with this {label} already exists.");
  }}
  const created = await db.{child}.create({{
    data: {{
      {label}: title,
      {amount}: value,
      ...(fkValue ? {{ {fk}: fkValue }} : {{}}),
      status: "{initial_status}",
    }},
  }});
  return new Response(JSON.stringify(created), {{ status: 201 }});
}}
"""


def task_spec(repo: Path, split: str, task_id: str) -> dict:
    spec = integration_contract(repo, split, task_id)
    suite = scenarios.load_split(repo, split, suite_version=2)
    entry = next(task for task in suite["tasks"] if task["id"] == task_id)
    cases = scenarios.oracle_cases(entry)
    if not cases:
        raise ValueError("Frozen integration cases were empty")
    spec["cases"] = cases
    spec["fixture"] = route_fixtures.fixture_rows(entry)
    spec["conventions"] = {
        "export": "default",
        "fetch": "relative URLs only; GET list on mount; POST on submit",
        "title_input": "text input whose accessible name or id mentions the label field",
        "amount_input": "numeric input whose accessible name or id mentions the amount field",
        "fk_select": "select whose accessible name mentions the relation; option value is the parent id",
        "submit": "button[type=submit] or a button whose text matches add|create|save|submit",
        "error_display": "role=alert element or visible text matching the error regex; must appear only after a failed submit",
        "total_display": "visible text mentioning total/count with the current number",
        "form_preserved": "after a failed submit the form fields keep their values",
        "error_text_re": ERROR_TEXT_RE,
        "total_text_re": TOTAL_TEXT_RE,
    }
    return spec
