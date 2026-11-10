"""Trusted Session-039 route-evaluation fixtures derived from frozen v2 contracts.

Everything produced here is authored teacher/trusted material: a Prisma schema
implementing the frozen schema-relationship requirements, a PrismaClient
provider, seed/reseed scripts and the frozen oracle cases. Nothing in this
module reads, generates or executes model output. The generated files are
staged into a temporary harness directory and bind-mounted read-only into the
restricted Docker evaluation container; the model-generated candidate is never
modified. Path parameters default to the in-container locations; the trusted
host smoke test may override them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import scenarios

ROUTE_RE = re.compile(r"/api/[a-z0-9-]+")
ENVELOPE_RE = re.compile(r"\{\s*([a-zA-Z][a-zA-Z0-9]*)\s*:\s*\[\.\.\.\],\s*total:\s*number\s*\}")
ROUTE_SKILLS = ("api-get-filter", "api-post-validation")
DB_ALIAS_SPECIFIERS = ("@/lib/db", "./lib/db", "../lib/db", "../../lib/db", "/lib/db", "lib/db")
DEFAULT_CLIENT_IMPORT = "/work/generated-client/index.js"


def fixture_rows(entry: dict) -> dict:
    """Independent copy of the frozen scenario fixture rows for one contract.

    Kept byte-equivalent to ``scenarios.build`` on purpose; a unit test guards
    the equality so this staging path cannot drift from the frozen plans.
    """
    fk = entry["entities"]["foreign_key"]
    measure = entry["fields"]["amount"]
    lo = entry["fields"]["min_inclusive"]
    states = entry["workflow"]
    return {
        "parents": [{"id": "parent-a"}, {"id": "parent-b"}],
        "children": [
            {"id": "sample-a", "title": "Amber", measure: lo, fk: "parent-a", "status": states[0]},
            {"id": "sample-b", "title": "Cobalt", measure: lo + 1, fk: "parent-a", "status": states[1]},
            {"id": "sample-c", "title": "Beacon", measure: lo + 2, fk: "parent-b", "status": states[2]},
        ],
    }


def prisma_schema(entry: dict, *, work_dir: str = "/work") -> str:
    """Trusted Prisma schema implementing the frozen v2 schema-relationship spec."""
    parent = entry["entities"]["parent"]
    child = entry["entities"]["child"]
    fk = entry["entities"]["foreign_key"]
    optional = entry["entities"]["foreign_key_mode"] == "optional"
    measure = entry["fields"]["amount"]
    initial_status = entry["workflow"][0]
    child_model = child.lower()
    parent_model = parent.lower()
    fk_field = f"{fk} String?" if optional else f"{fk} String"
    relation = (
        f"  {parent_model} {parent}? @relation(fields: [{fk}], references: [id], onDelete: SetNull)"
        if optional
        else f"  {parent_model} {parent} @relation(fields: [{fk}], references: [id], onDelete: Restrict)"
    )
    return f"""// TRUSTED Session-039 fixture — AUTHORED_SCHEMA_NOT_QWEN_CODE
// Derived deterministically from the frozen v2 contract for {entry['id']}.
datasource db {{
  provider = "sqlite"
  url      = "file:{work_dir}/db.sqlite"
}}

generator client {{
  provider   = "prisma-client-js"
  output     = "{work_dir}/generated-client"
  engineType = "library"
}}

model {parent} {{
  id          String   @id @default(cuid())
  {child_model} {child}[]

  @@map("{parent_model}s")
}}

model {child} {{
  id          String  @id @default(cuid())
  title       String
  {measure}   Int
  {fk_field}
  status      String  @default("{initial_status}")
  {relation}

  @@map("{child_model}s")
}}
"""


def db_client_ts(*, client_import: str = DEFAULT_CLIENT_IMPORT) -> str:
    """Trusted PrismaClient provider the candidate is resolved against."""
    return f"""// TRUSTED Session-039 fixture — AUTHORED_DB_PROVIDER_NOT_QWEN_CODE
// Provided by the evaluation harness; never shown to, or written by, the model.
import prismaPkg from "{client_import}";

const {{ PrismaClient }} = prismaPkg;
export const db = new PrismaClient({{
  log: ["error"],
}});
"""


def fixture_mjs(entry: dict, *, client_import: str = DEFAULT_CLIENT_IMPORT) -> str:
    """Trusted reseed module: reset the database to exactly the frozen fixture rows."""
    parent_client = entry["entities"]["parent"].lower()
    child_client = entry["entities"]["child"].lower()
    rows = fixture_rows(entry)
    parents_js = json.dumps(rows["parents"], sort_keys=True)
    children_js = json.dumps(rows["children"], sort_keys=True)
    return f"""// TRUSTED Session-039 fixture — AUTHORED_RESEED_NOT_QWEN_CODE
import prismaPkg from "{client_import}";

export async function seedFixture(db) {{
  // Children first: required-FK Restrict and optional-FK SetNull both stay safe.
  await db.{child_client}.deleteMany();
  await db.{parent_client}.deleteMany();
  for (const row of {parents_js}) {{
    await db.{parent_client}.create({{ data: row }});
  }}
  for (const row of {children_js}) {{
    await db.{child_client}.create({{ data: row }});
  }}
}}
"""


def seed_mjs(*, client_import: str = DEFAULT_CLIENT_IMPORT) -> str:
    """Trusted initial seed entry point (delegates to the reseed module)."""
    return f"""// TRUSTED Session-039 fixture — AUTHORED_SEED_NOT_QWEN_CODE
import {{ seedFixture }} from "./fixture.mjs";
import prismaPkg from "{client_import}";
const {{ PrismaClient }} = prismaPkg;
const db = new PrismaClient();
await seedFixture(db);
await db.$disconnect();
"""


def route_contract(repo: Path, split: str, task_id: str) -> dict:
    """Load one frozen GET/POST contract and extract the trusted routing facts."""
    suite = scenarios.load_split(repo, split, suite_version=2)
    entries = [task for task in suite["tasks"] if task["id"] == task_id]
    if len(entries) != 1 or entries[0]["skill"] not in ROUTE_SKILLS:
        raise ValueError("Expected one frozen api-get-filter/api-post-validation task in train/dev")
    entry = entries[0]
    requirements = " ".join(entry["requirements"])
    routes = sorted(set(ROUTE_RE.findall(requirements)))
    if len(routes) != 1:
        raise ValueError(f"Contract {task_id} does not state exactly one /api/ route: {routes}")
    spec: dict = {"task_id": task_id, "skill": entry["skill"], "route_path": routes[0]}
    if entry["skill"] == "api-get-filter":
        envelopes = sorted(set(ENVELOPE_RE.findall(requirements)))
        if len(envelopes) != 1:
            raise ValueError(f"Contract {task_id} does not state exactly one list envelope: {envelopes}")
        spec["envelope_key"] = envelopes[0]
    spec["entities"] = {
        "parent_client": entry["entities"]["parent"].lower(),
        "child_client": entry["entities"]["child"].lower(),
        "parent_table": entry["entities"]["parent"].lower() + "s",
        "child_table": entry["entities"]["child"].lower() + "s",
        "foreign_key": entry["entities"]["foreign_key"],
        "foreign_key_optional": entry["entities"]["foreign_key_mode"] == "optional",
    }
    spec["fields"] = dict(entry["fields"])
    spec["workflow"] = list(entry["workflow"])
    return spec


def task_spec(repo: Path, split: str, task_id: str) -> dict:
    """Full trusted task.json staged for the in-container route runner."""
    spec = route_contract(repo, split, task_id)
    suite = scenarios.load_split(repo, split, suite_version=2)
    entry = next(task for task in suite["tasks"] if task["id"] == task_id)
    cases = scenarios.oracle_cases(entry)
    if spec["skill"] == "api-get-filter":
        valid = all(
            isinstance(c.get("params"), dict) and isinstance(c.get("expected_status"), int)
            and isinstance(c.get("expected_titles"), list) and isinstance(c.get("expected_total"), int)
            for c in cases
        )
    else:
        valid = all(
            isinstance(c.get("body"), dict) and isinstance(c.get("expected_status"), int)
            and isinstance(c.get("expected_persist_delta"), int)
            for c in cases
        )
    if not cases or not valid:
        raise ValueError("Frozen route behavior cases were incomplete for staging")
    spec["cases"] = cases
    spec["fixture"] = fixture_rows(entry)
    spec["db_alias_specifiers"] = list(DB_ALIAS_SPECIFIERS)
    spec["label_field"] = entry["fields"]["label"]
    return spec
