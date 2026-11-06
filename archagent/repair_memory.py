"""Reusable repair-pattern memory (mission section 9).

Every accepted repair produces a structured record:
  requirement, failed source excerpt, failure message, repaired excerpt,
  corrected behavior, programming principle, category, affected contracts.

Records accumulate in experiments/zai-taskflow/repair_memory/*.json and can
be retrieved into prompts for unfamiliar tasks (transfer test).  This is
in-context pattern reuse only — it never touches model weights.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

CATEGORIES = (
    "variable_tracking", "type_consistency", "api_response_structure",
    "state_management", "persistence", "async_operations",
    "component_integration", "validation", "syntax", "control_flow",
)

_PRINCIPLES = [
    (re.compile(r"Assignment to constant variable", re.I),
     "js", "A const binding cannot be reassigned; mutable state needs let.",
     "variable_tracking"),
    (re.compile(r"is not a function|TypeError: .*undefined", re.I),
     "js", "Call methods only on values that exist; guard optional lookups.",
     "type_consistency"),
    (re.compile(r"ENOENT|no such file or directory", re.I),
     "fs", "Check the data file exists before reading; start empty when it does not.",
     "persistence"),
    (re.compile(r"Unexpected token|SyntaxError|transform .* error", re.I),
     "js", "Balanced braces and complete expressions are required for parsing.",
     "syntax"),
    (re.compile(r"404|not found", re.I),
     "api", "Distinguish unknown resources (404) from invalid input (400).",
     "api_response_structure"),
    (re.compile(r"status \d+ \(want \d+\)", re.I),
     "api", "Each route must answer with the exact contract status code.",
     "api_response_structure"),
    (re.compile(r"res\.ok|fetch", re.I),
     "ui", "fetch resolves on HTTP errors too; check res.ok before parsing.",
     "async_operations"),
    (re.compile(r"expected \d+ items|length", re.I),
     "store", "Filters compose: apply every provided key, match-all when absent.",
     "validation"),
]


def classify(failure_detail: str) -> tuple[str, str]:
    """(principle, category) inferred from the failure message."""
    for pattern, _, principle, category in _PRINCIPLES:
        if pattern.search(failure_detail or ""):
            return principle, category
    return "Match the documented contract exactly.", "validation"


def excerpt(source: str, anchor_line: int | None = None,
            window: int = 6) -> str:
    lines = source.splitlines()
    if anchor_line is None:
        return "\n".join(lines[:window])
    lo = max(0, anchor_line - window // 2)
    hi = min(len(lines), lo + window)
    return "\n".join(f"{i+1}: {lines[i]}" for i in range(lo, hi))


def record_repair(*, role: str, requirement: str, failed_source: str,
                  failure_detail: str, repaired_source: str,
                  corrected_behavior: str, anchor_line: int | None = None,
                  contract_refs: list[str] | None = None) -> dict:
    principle, category = classify(failure_detail)
    return {
        "id": f"{role}-{int(time.time()*1000)%100000}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "role": role,
        "requirement": requirement[:400],
        "failed_excerpt": excerpt(failed_source, anchor_line),
        "failure_message": str(failure_detail)[:300],
        "repaired_excerpt": excerpt(repaired_source, anchor_line),
        "corrected_behavior": corrected_behavior[:300],
        "principle": principle,
        "category": category,
        "contract_refs": contract_refs or [],
    }


class RepairMemory:
    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def add(self, record: dict) -> None:
        path = self.dir / f"{record['id']}.json"
        path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf8")

    def all(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf8"))
                for p in sorted(self.dir.glob("*.json"))]

    def retrieve(self, role: str, failure_detail: str, k: int = 3) -> list[dict]:
        """Rank by (same role, category match, keyword overlap)."""
        records = self.all()
        _, cat = classify(failure_detail)

        def score(r: dict) -> int:
            s = 0
            if r["role"] == role:
                s += 4
            if r["category"] == cat:
                s += 3
            words = set(re.findall(r"[a-z]{4,}", failure_detail.lower()))
            mine = set(re.findall(r"[a-z]{4,}",
                                  (r["failure_message"] + " " + r["principle"]).lower()))
            s += min(3, len(words & mine))
            return s

        return sorted(records, key=score, reverse=True)[:k]

    def prompt_block(self, role: str, failure_detail: str, k: int = 3) -> str:
        """Retrieved patterns formatted for a repair prompt (transfer)."""
        recs = self.retrieve(role, failure_detail, k)
        if not recs:
            return ""
        out = ["/* Previously verified correction patterns (concepts only): */"]
        for r in recs:
            out.append(f"/* - {r['principle']} (category: {r['category']}) "
                       f"failure was: {r['failure_message'][:120]} */")
        return "\n".join(out) + "\n\n"
