"""Trusted Session-040 react-interaction fixtures derived from frozen v2 contracts.

Everything here is teacher-authored trusted material: the conventions the
runner checks (data prop, default export, labeled native controls, rendered
filtered items, explicit empty state), the frozen fixture rows (identical to
the route evaluator's) and the oracle cases straight from the frozen v2
suite. Nothing reads, generates or executes model output. The staged files
are bind-mounted read-only into the restricted execution tier; the candidate
file is never modified.
"""

from __future__ import annotations

import json
from pathlib import Path

from archagent.s039 import route_fixtures, scenarios

REACT_SKILL = "react-interaction"

# Case-sensitive distinct-title counting: the runner counts how many of the
# fixture titles appear anywhere in the rendered text. A component therefore
# must not render filtered-out items (CSS hiding is not accepted — jsdom
# cannot compute layout).
EMPTY_STATE_RE = (r"no (items|results|records|matches|entries|things|shows)|"
                  r"nothing (found|to show|matches)|nothing yet|empty")
CLEAR_BUTTON_RE = r"(clear|reset)"
STATUS_NAME_RE = r"status"


def task_spec(repo: Path, split: str, task_id: str) -> dict:
    """Full trusted task.json staged for the in-sandbox react runner."""
    suite = scenarios.load_split(repo, split, suite_version=2)
    entries = [task for task in suite["tasks"] if task["id"] == task_id]
    if len(entries) != 1 or entries[0]["skill"] != REACT_SKILL:
        raise ValueError("Expected one frozen react-interaction task in train/dev")
    entry = entries[0]
    cases = scenarios.oracle_cases(entry)
    events = {case.get("event") for case in cases}
    allowed = {"initial-render", "type-search", "choose-status", "search-and-status",
               "clear-filters", "keyboard-only-interaction", "viewport-320"}
    if not cases or not events <= allowed:
        raise ValueError(f"React oracle events outside supported set: {events - allowed}")
    fixture = route_fixtures.fixture_rows(entry)
    return {
        "task_id": task_id,
        "skill": REACT_SKILL,
        "conventions": {
            "export": "default",
            "prop": "data",
            "row_shape": ["id", entry["fields"]["label"], entry["fields"]["amount"],
                          entry["entities"]["foreign_key"], "status"],
            "counting": "distinct fixture titles case-sensitively present in rendered text",
            "filtered_items_must_not_render": True,
            "search_input": "first text/search input, labeled",
            "status_filter": "a select whose accessible name mentions status; option value equals the workflow state",
            "clear_button": "button whose text matches /clear|reset/i",
            "empty_state_re": EMPTY_STATE_RE,
            "clear_button_re": CLEAR_BUTTON_RE,
            "status_name_re": STATUS_NAME_RE,
        },
        "fields": dict(entry["fields"]),
        "workflow": list(entry["workflow"]),
        "fixture": fixture,
        "titles": [row[entry["fields"]["label"]] for row in fixture["children"]],
        "cases": cases,
    }
