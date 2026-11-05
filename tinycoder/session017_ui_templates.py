"""Contract-derived trusted UI layout templates, no model inference."""
from __future__ import annotations

import json


def contract_ui(task: dict):
    """Deterministic React shell generated from the PUBLIC contract alone.

    The model is still responsible for Python reasoning and Express behavior.
    This template has no task examples, reference outputs or heldout inputs.
    """
    contract = task["contract"]
    heading = json.dumps(contract["heading"])
    test_id = json.dumps(contract["ui_testid"])
    return ("const React = require('react');\n"
            "function ResultView({data}) {\n"
            "  const value = data.value;\n"
            "  const shown = value === null ? 'none' :\n"
            "    Array.isArray(value) ? value.map(String).join(', ') : String(value);\n"
            f"  return <section data-testid={{{test_id}}}>"
            f"<h3>{{{heading}}}</h3><output>{{shown}}</output></section>;\n"
            "}\n")
