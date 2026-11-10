"""Freeze a cross-domain task curriculum without model calls or answers.

Tasks define *requirements*, not working solutions. The optional hidden
suite must be kept out of model generation, training and feedback loops.
This module does no inference, test execution, fine-tuning or downloading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


# All domains are new relative to Sessions 035–038A. Split by entire domain,
# never by component. Deliberately vary field names and workflow states.
DOMAINS = {
    "train": [
        ("aquarium", "Tank", "FeedLog", "feedGrams", 1, 600, ("draft", "scheduled", "served"), False),
        ("observatory", "Telescope", "Exposure", "seconds", 2, 5400, ("queued", "aligned", "captured"), True),
        ("recycling", "Depot", "Collection", "weightKg", 1, 1000, ("requested", "assigned", "collected"), False),
        ("filmset", "Camera", "Take", "durationSec", 3, 1200, ("planned", "filmed", "approved"), True),
        ("makerspace", "Laser", "CutJob", "runMinutes", 1, 180, ("submitted", "prepared", "finished"), False),
        ("artmarket", "Gallery", "ArtworkSale", "priceUsd", 5, 100000, ("listed", "reserved", "sold"), True),
        ("wildlife", "Sanctuary", "Survey", "count", 1, 500, ("reported", "checked", "released"), False),
        ("foodbank", "Pantry", "Parcel", "units", 1, 300, ("packed", "routed", "delivered"), True),
        ("landregistry", "ParcelZone", "Inspection", "areaSqm", 10, 90000, ("opened", "inspected", "closed"), False),
    ],
    "dev": [
        ("radiostation", "Transmitter", "Broadcast", "airtimeMin", 1, 360, ("drafted", "cleared", "aired"), True),
        ("tailorshop", "Worktable", "Order", "fabricCm", 10, 2000, ("measured", "stitched", "fitted"), False),
        ("sportsarena", "Court", "Practice", "participants", 2, 100, ("registered", "confirmed", "completed"), True),
    ],
    "holdout": [
        ("mountainrescue", "Outpost", "Dispatch", "distanceKm", 1, 300, ("received", "mobilized", "resolved"), False),
        ("textilemill", "Loom", "ProductionRun", "meters", 1, 10000, ("scheduled", "spun", "packed"), True),
        ("trafficops", "Junction", "SignalAudit", "delayMs", 1, 60000, ("created", "checked", "deployed"), False),
        ("heritagemuseum", "Vault", "Conservation", "hours", 1, 2000, ("logged", "treated", "exhibited"), True),
    ],
}

SKILLS = (
    "schema-relationship", "api-get-filter", "api-post-validation",
    "state-invariant", "react-interaction", "fullstack-integration",
)


def _task(domain: tuple, skill: str) -> dict:
    slug, parent, child, amount, lower, upper, states, optional_fk = domain
    prefix = slug.replace("-", "")
    parent_name = parent[0].lower() + parent[1:]
    child_name = child[0].lower() + child[1:]
    relationship = "optional" if optional_fk else "required"
    base = {
        "id": f"{slug}:{skill}",
        "domain": slug,
        "skill": skill,
        "contract_version": 1,
        "status": "SPEC_ONLY_NOT_GENERATED",
        "user_story": f"Manage {child} records linked to {parent} in the {slug} service.",
        "entities": {"parent": parent, "child": child, "foreign_key": f"{parent_name}Id", "foreign_key_mode": relationship},
        "fields": {"amount": amount, "min_inclusive": lower, "max_inclusive": upper, "label": "title"},
        "workflow": list(states),
        "negative_cases_required": [],
        "positive_cases_required": [],
        "provenance": "AUTHOR_SPEC_NOT_QWEN_CODE",
    }
    if skill == "schema-relationship":
        base["requirements"] = [
            f"Write the Prisma models for {parent} and {child}, with correct one-to-many relation sides.",
            f"The {child}.{parent_name}Id foreign key is {relationship}; its relation field must have matching nullability.",
            "Use String @id @default(cuid()) primary keys and an Int measurement field.",
            "Declared delete semantics must match foreign-key optionality: SetNull if optional, Restrict if required.",
        ]
        base["positive_cases_required"] = ["valid-parent", "valid-child", "relation-traversal"]
        base["negative_cases_required"] = ["bogus-fk", "nullable-fk-boundary", "delete-parent-semantics"]
    elif skill == "api-get-filter":
        base["requirements"] = [
            f"Implement Next.js GET /api/{prefix}-{child_name}s using db.{child_name}.findMany.",
            "Use searchParams 'q' as a case-insensitive title substring filter only when supplied.",
            f"Filter by optional {parent_name}Id, order by title ascending, include {parent_name}.",
            f"Return {{ {child_name}s: [...], total: number }} with status 200; empty results return [] and 0.",
        ]
        base["positive_cases_required"] = ["list-all", "filter-multiple", "filter-one", "no-matches"]
        base["negative_cases_required"] = ["missing-query", "unknown-parent-filter", "no-accidental-cross-domain-data"]
    elif skill == "api-post-validation":
        base["requirements"] = [
            f"Implement POST /api/{prefix}-{child_name}s; trim required title and validate {amount} as a finite integer.",
            f"Enforce {lower} <= {amount} <= {upper} with HTTP 400 on missing/invalid/out-of-range values.",
            f"Check {parent}.id existence with findUnique; unknown parent returns HTTP 404, except null is allowed if FK optional.",
            f"Reject duplicate title within one {parent} with HTTP 409. Create only after every check and return 201.",
        ]
        base["positive_cases_required"] = ["min-boundary", "max-boundary", "persists-valid-create"]
        base["negative_cases_required"] = ["empty-title", "not-a-number", "non-integer", "below-min", "above-max", "unknown-parent", "duplicate-title", "no-write-on-error"]
    elif skill == "state-invariant":
        base["requirements"] = [
            f"Implement canAdvance{child}(current, next): boolean for exact transitions {states[0]}→{states[1]} and {states[1]}→{states[2]}.",
            "Every other transition is false, including unknown states, skips, reversals and unchanged states.",
            "Use these exact domain-specific words; do not copy stage names from any illustrative demo.",
        ]
        base["positive_cases_required"] = ["first-transition", "second-transition"]
        base["negative_cases_required"] = ["same-state", "skip-state", "reverse-state", "unknown-state", "demo-vocabulary-copy"]
    elif skill == "react-interaction":
        base["requirements"] = [
            f"Build a responsive React component listing {child} items from a provided data prop; no network call required.",
            "Provide a labeled search field, an accessible status filter and a clear-filters button.",
            f"Render title, {amount} and current workflow status, with an explicit no-results empty state.",
            "Keyboard operation and a 320px mobile viewport must remain usable without horizontal overflow.",
        ]
        base["positive_cases_required"] = ["all-items", "search", "status-filter", "clear", "mobile-320", "keyboard"]
        base["negative_cases_required"] = ["empty-result-state", "missing-label", "overflow", "filter-combination"]
    elif skill == "fullstack-integration":
        base["requirements"] = [
            f"Connect a React create form to the GET/POST route and persisted {child} model in this domain.",
            "After HTTP 201, update the visible list and total without a full-page reload.",
            "Display 400/404/409 validation failures and preserve form data for correction.",
            "A subsequent GET must return the persisted item; no fake local-only success is accepted.",
        ]
        base["positive_cases_required"] = ["create-201", "visible-immediately", "get-persisted", "refresh-survives"]
        base["negative_cases_required"] = ["post-400", "post-404", "post-409", "no-phantom-create", "refresh-after-error"]
    else:
        raise ValueError(f"Unsupported task skill: {skill}")
    return base


def build(split: str) -> dict:
    if split not in DOMAINS:
        raise ValueError("Unknown split")
    tasks = [_task(d, skill) for d in DOMAINS[split] for skill in SKILLS]
    return {"session": "039", "split": split, "role": "CONTRACTS_ONLY_NOT_TRAINING_DATA",
            "tasks": tasks, "generation_permitted": split != "holdout",
            "sealed_until_final_scoring": split == "holdout"}


def _serialized(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def frozen_files() -> dict[str, bytes]:
    return {f"{s}.json": _serialized(build(s)) for s in DOMAINS}


def manifest() -> dict:
    files = frozen_files()
    return {
        "session": "039", "freeze_version": 1,
        "frozen_before_any_s039_inference": True,
        "trainable_records": 0,
        "holdout_rule": "Do not load/inspect holdout specs or their oracles in generation, training, controller feedback, hyperparameter search or retrieval",
        "splits": {s: {"domains": [d[0] for d in DOMAINS[s]],
                        "task_count": len(DOMAINS[s]) * len(SKILLS),
                        "sha256": hashlib.sha256(files[f"{s}.json"]).hexdigest()}
                   for s in DOMAINS},
    }


def freeze(directory: Path, *, check_only: bool) -> dict:
    """Refuse to rewrite already-frozen files; check digests on resume."""
    files = frozen_files()
    files["MANIFEST.json"] = _serialized(manifest())
    if check_only:
        for name, content in files.items():
            target = directory / name
            if not target.is_file() or target.read_bytes() != content:
                raise ValueError(f"Frozen curriculum drift: {name}")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        existing = [name for name in files if (directory / name).exists()]
        if existing:
            raise FileExistsError(f"Refusing to overwrite frozen files: {existing}")
        for name, content in files.items():
            (directory / name).write_bytes(content)
    return manifest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=Path("experiments/z039-generalization-learning/suite"))
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = p.parse_args()
    result = freeze(args.dir, check_only=args.check)
    print(json.dumps({"splits": {k: v["task_count"] for k, v in result["splits"].items()}, "mode": "check" if args.check else "freeze", "training": False}))


if __name__ == "__main__":
    main()
