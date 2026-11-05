"""Reusable, testable teacher feedback for Qwen with frozen parameters.

This is external prompt memory, NOT optimization of a neural network. It never
reads private holdout examples or executes generated code. Model code still
requires the repository's isolated Docker evaluation pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_BANK = Path(__file__).resolve().parents[1] / "experiments/session026_reasoning_patterns.json"
TOKEN = re.compile(r"[a-z][a-z0-9_.-]*", flags=re.IGNORECASE)


def _terms(value: str) -> set[str]:
    return set(TOKEN.findall(value.lower()))


def load_bank(path: Path = DEFAULT_BANK) -> dict[str, Any]:
    bank = json.loads(path.read_text(encoding="utf-8"))
    if bank.get("schema") != "public_teacher_patterns_v1":
        raise ValueError("Unknown mentor memory schema")
    if bank.get("training_steps") != 0 or bank.get("parameter_count") != 494032768:
        raise ValueError("Mentor memory cannot imply parameter training or scaling")
    patterns = bank.get("patterns")
    if not isinstance(patterns, list):
        raise ValueError("Malformed patterns")
    ids: set[str] = set()
    for pattern in patterns:
        if not isinstance(pattern, dict):
            raise ValueError("Malformed pattern")
        if pattern.get("source") not in {"session023_public_feedback", "session024_public_feedback"}:
            raise ValueError("Pattern requires verified public source")
        if not all(
            isinstance(pattern.get(field), str) and pattern[field].strip()
            for field in ("id", "domain", "observed_failure", "general_rule", "verification")
        ):
            raise ValueError("Incomplete pattern")
        if pattern["id"] in ids:
            raise ValueError("Duplicate pattern")
        ids.add(pattern["id"])
        if not isinstance(pattern.get("tags"), list) or not all(
            isinstance(tag, str) and tag for tag in pattern["tags"]
        ):
            raise ValueError("Invalid tags")
    return bank


def retrieve_patterns(
    task: str, *, domain: str, bank: dict[str, Any], max_patterns: int = 2
) -> list[dict[str, Any]]:
    """Select abstraction-only lessons by interface/domain and lexical overlap."""
    if max_patterns < 0 or max_patterns > 4:
        raise ValueError("max_patterns must be in 0..4")
    task_terms = _terms(task)
    scored = []
    for pattern in bank["patterns"]:
        if pattern["domain"] != domain:
            continue
        overlap = len(task_terms.intersection(_terms(" ".join(pattern["tags"]))))
        if overlap:
            scored.append((overlap, pattern["id"], pattern))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored[:max_patterns]]


def assemble_student_prompt(task: str, *, domain: str, bank: dict[str, Any]) -> str:
    """Construct a bounded *before-generation* checklist, without solutions."""
    if not task.strip():
        raise ValueError("Cannot build an empty task")
    matched = retrieve_patterns(task, domain=domain, bank=bank)
    steps = [
        "PRIVATE WORKING CHECKLIST (do not output these notes as code):",
        "1. Read the current task's exact inputs, outputs, response envelopes and interface names.",
        "2. Transfer structures from analogies, never their unrelated names or data.",
        "3. Make the smallest code change that satisfies the current contract.",
        "4. After a PUBLIC test failure, classify: method name, response shape, value, or syntax.",
    ]
    if matched:
        steps.append("RETRIEVED PUBLIC TEACHER LESSONS:")
        for pattern in matched:
            steps.append(f"- {pattern['general_rule']} Verify: {pattern['verification']}")
    steps.extend(["CURRENT TASK:", task.strip(), "OUTPUT ONLY THE REQUESTED CODE."])
    return "\n".join(steps)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--domain", choices=("express", "react", "python"), required=True)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    args = parser.parse_args()
    print(assemble_student_prompt(args.task, domain=args.domain, bank=load_bank(args.bank)))


if __name__ == "__main__":
    main()
