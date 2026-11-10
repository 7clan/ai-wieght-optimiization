"""Create trusted black-box test *plans* from frozen Session-039 contracts.

No model-generated code is evaluated here. Running actual HTTP/UI/Prisma
tests needs a separate, isolated and independently validated executor.
The holdout may not be loaded until final evaluation is explicitly unlocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SUITE = Path("experiments/z039-generalization-learning/suite")
DEFAULT_OUT = Path("experiments/z039-generalization-learning/scenarios")


def _bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def load_split(root: Path, split: str, *, final_score_unlocked: bool = False, suite_version: int = 1) -> dict:
    if split not in ("train", "dev", "holdout"):
        raise ValueError("Unknown curriculum split")
    if split == "holdout" and not final_score_unlocked:
        raise PermissionError("Holdout is sealed until all predictions and decisions are frozen")
    if suite_version not in (1, 2):
        raise ValueError("Unknown suite version")
    directory = root / (SUITE if suite_version == 1 else SUITE.parent / "suite-v2")
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    raw = (directory / f"{split}.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["splits"][split]["sha256"]:
        raise ValueError("Frozen suite hash mismatch")
    suite = json.loads(raw)
    if suite.get("split") != split:
        raise ValueError("Split metadata mismatch")
    return suite


def oracle_cases(task: dict) -> list[dict]:
    """Return requirements-driven scenarios, *not* tested successes."""
    skill = task["skill"]
    fk = task["entities"]["foreign_key"]
    optional = task["entities"]["foreign_key_mode"] == "optional"
    value = task["fields"]["amount"]
    lo = task["fields"]["min_inclusive"]
    hi = task["fields"]["max_inclusive"]
    states = task["workflow"]
    if skill == "schema-relationship":
        return [
            {"name": "valid-parent", "action": "insert-parent", "expected": "success"},
            {"name": "valid-child", "action": "insert-child", "record": {fk: "parent-a"}, "expected": "success"},
            {"name": "bogus-fk", "action": "insert-child", "record": {fk: "absent"}, "expected": "foreign-key-reject"},
            {"name": "nullable-fk-boundary", "action": "insert-child", "record": {fk: None}, "expected": "success" if optional else "not-null-reject"},
            {"name": "delete-parent-semantics", "action": "delete-parent-with-child", "expected": "set-null" if optional else "restrict"},
            {"name": "relation-traversal", "action": "load-parent-with-children", "expected": "child-visible"},
        ]
    if skill == "api-get-filter":
        return [
            {"name": "list-all", "params": {}, "expected_status": 200, "expected_titles": ["Amber", "Beacon", "Cobalt"], "expected_total": 3},
            {"name": "filter-one", "params": {"q": "beac"}, "expected_status": 200, "expected_titles": ["Beacon"], "expected_total": 1},
            {"name": "case-insensitive", "params": {"q": "AMBER"}, "expected_status": 200, "expected_titles": ["Amber"], "expected_total": 1},
            {"name": "filter-by-parent", "params": {fk: "parent-a"}, "expected_status": 200, "expected_titles": ["Amber", "Cobalt"], "expected_total": 2},
            {"name": "no-matches", "params": {"q": "zzz-not-present"}, "expected_status": 200, "expected_titles": [], "expected_total": 0},
            {"name": "combined-filter", "params": {"q": "beacon", fk: "parent-a"}, "expected_status": 200, "expected_titles": [], "expected_total": 0},
        ]
    if skill == "api-post-validation":
        valid = {"title": "New item", value: lo, fk: "parent-a"}
        return [
            {"name": "min-boundary", "body": valid, "expected_status": 201, "expected_persist_delta": 1},
            {"name": "max-boundary", "body": {**valid, value: hi}, "expected_status": 201, "expected_persist_delta": 1},
            {"name": "empty-title", "body": {**valid, "title": "  "}, "expected_status": 400, "expected_persist_delta": 0},
            {"name": "not-a-number", "body": {**valid, value: "abc"}, "expected_status": 400, "expected_persist_delta": 0},
            {"name": "non-integer", "body": {**valid, value: lo + 0.25}, "expected_status": 400, "expected_persist_delta": 0},
            {"name": "below-min", "body": {**valid, value: lo - 1}, "expected_status": 400, "expected_persist_delta": 0},
            {"name": "above-max", "body": {**valid, value: hi + 1}, "expected_status": 400, "expected_persist_delta": 0},
            {"name": "unknown-parent", "body": {**valid, fk: "missing"}, "expected_status": 404, "expected_persist_delta": 0},
            {"name": "duplicate-title", "body": {**valid, "title": "Amber"}, "expected_status": 409, "expected_persist_delta": 0},
            {"name": "parent-null", "body": {**valid, fk: None}, "expected_status": 201 if optional else 400, "expected_persist_delta": 1 if optional else 0},
        ]
    if skill == "state-invariant":
        a, b, c = states
        return [
            {"name": "first-transition", "inputs": [a, b], "expected": True},
            {"name": "second-transition", "inputs": [b, c], "expected": True},
            {"name": "same-state", "inputs": [a, a], "expected": False},
            {"name": "skip-state", "inputs": [a, c], "expected": False},
            {"name": "reverse-state", "inputs": [c, b], "expected": False},
            {"name": "unknown-state", "inputs": ["not-a-real-state", b], "expected": False},
            {"name": "demo-vocabulary-copy", "inputs": ["raw", "edited"], "expected": False},
        ]
    if skill == "react-interaction":
        return [
            {"name": "all-items", "event": "initial-render", "expected_count": 3},
            {"name": "search", "event": "type-search", "query": "beacon", "expected_count": 1},
            {"name": "status-filter", "event": "choose-status", "status": states[1], "expected_count": 1},
            {"name": "combined-filter", "event": "search-and-status", "query": "amber", "status": states[2], "expected_count": 0},
            {"name": "empty-result-state", "event": "type-search", "query": "not-found", "expected": "explicit-empty-state"},
            {"name": "clear", "event": "clear-filters", "expected_count": 3},
            {"name": "keyboard", "event": "keyboard-only-interaction", "expected": "operable-and-labeled"},
            {"name": "mobile-320", "event": "viewport-320", "expected": "no-horizontal-overflow"},
        ]
    if skill == "fullstack-integration":
        return [
            {"name": "create-201", "event": "submit-form", "body": {"title": "New item", value: lo, fk: "parent-a"}, "expected_status": 201},
            {"name": "visible-immediately", "event": "check-dom-after-submit", "expected": "new-item-in-list-and-total-incremented"},
            {"name": "get-persisted", "event": "http-get", "expected": "new-item-present"},
            {"name": "refresh-survives", "event": "reload-and-http-get", "expected": "new-item-present"},
            {"name": "post-400", "event": "submit-form", "body": {"title": " ", value: lo}, "expected_status": 400, "expected": "error-visible-no-new-item"},
            {"name": "post-404", "event": "submit-form", "body": {"title": "Valid", value: lo, fk: "missing"}, "expected_status": 404, "expected": "error-visible-no-new-item"},
            {"name": "post-409", "event": "submit-duplicate", "expected_status": 409, "expected": "error-visible-no-new-item"},
            {"name": "refresh-after-error", "event": "reload-and-http-get", "expected": "no-phantom-record"},
        ]
    raise ValueError(f"Unknown skill: {skill}")


def build(root: Path, split: str, *, final_score_unlocked: bool = False, suite_version: int = 1) -> dict:
    suite = load_split(root, split, final_score_unlocked=final_score_unlocked, suite_version=suite_version)
    cases = []
    for t in suite["tasks"]:
        fk = t["entities"]["foreign_key"]
        measure = t["fields"]["amount"]
        lo = t["fields"]["min_inclusive"]
        states = t["workflow"]
        # Fixture is trusted independent setup, NEVER part of a generated answer.
        fixture = {
            "parents": [{"id": "parent-a"}, {"id": "parent-b"}],
            "children": [
                {"id": "sample-a", "title": "Amber", measure: lo, fk: "parent-a", "status": states[0]},
                {"id": "sample-b", "title": "Cobalt", measure: lo + 1, fk: "parent-a", "status": states[1]},
                {"id": "sample-c", "title": "Beacon", measure: lo + 2, fk: "parent-b", "status": states[2]},
            ],
        }
        cases.append({"task_id": t["id"], "skill": t["skill"], "status": "UNEXECUTED_BEHAVIOR_SCENARIOS",
                      "fixture": fixture, "cases": oracle_cases(t)})
    result = {"session": "039", "split": split, "origin": "TRUSTED_ORACLE_PLAN_NOT_QWEN_CODE",
              "candidate_execution_count": 0, "training_eligible": 0, "tasks": cases}
    if suite_version != 1:
        result["suite_version"] = suite_version
    return result


def write(root: Path, split: str, target: Path, *, check: bool, suite_version: int = 1) -> None:
    if split == "holdout":
        raise PermissionError("Never export holdout scenarios before final scoring")
    content = _bytes(build(root, split, suite_version=suite_version))
    if check:
        if not target.is_file() or target.read_bytes() != content:
            raise ValueError("Scenario plan drift")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError("Refusing to overwrite scenario plan")
        target.write_bytes(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--split", choices=["train", "dev"], required=True)
    parser.add_argument("--suite-version", type=int, choices=[1, 2], default=1)
    parser.add_argument("--out-dir", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directory = args.out_dir or (DEFAULT_OUT if args.suite_version == 1 else DEFAULT_OUT.parent / "scenarios-v2")
    write(args.repo, args.split, directory / f"{args.split}.json", check=args.check, suite_version=args.suite_version)
    print(f"{args.split} scenario plan {'checked' if args.check else 'written'}; candidate code executed: 0")


if __name__ == "__main__":
    main()
