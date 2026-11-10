"""Trusted Session-040 schema-relationship fixtures derived from frozen v2 contracts.

Teacher-authored trusted material: contract facts for the candidate schema
(model names, FK field, optionality, onDelete semantics, status default) and
the behavioral probe plan executed against a database built FROM the
candidate's own schema. Nothing here reads, generates or executes model
output at fixture-build time; the runner stages a normalized COPY of the
candidate schema (datasource/generator redirects only) into /work.
"""

from __future__ import annotations

import json
from pathlib import Path

from archagent.s039 import scenarios

SCHEMA_SKILL = "schema-relationship"


def task_spec(repo: Path, split: str, task_id: str) -> dict:
    suite = scenarios.load_split(repo, split, suite_version=2)
    entries = [task for task in suite["tasks"] if task["id"] == task_id]
    if len(entries) != 1 or entries[0]["skill"] != SCHEMA_SKILL:
        raise ValueError("Expected one frozen schema-relationship task in train/dev")
    entry = entries[0]
    return {
        "task_id": task_id,
        "skill": SCHEMA_SKILL,
        "entities": {
            "parent": entry["entities"]["parent"],
            "child": entry["entities"]["child"],
            "foreign_key": entry["entities"]["foreign_key"],
            "foreign_key_optional": entry["entities"]["foreign_key_mode"] == "optional",
        },
        "fields": dict(entry["fields"]),
        "workflow": list(entry["workflow"]),
        "requirements": list(entry["requirements"]),
        "probes": [
            "parent-create",
            "child-required-fields-present",
            "child-create-valid-fk",
            "fk-nullability-matches-contract",
            "bogus-fk-rejected",
            "on-delete-semantics",
            "status-default",
        ],
    }
