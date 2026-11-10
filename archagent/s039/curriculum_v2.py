"""Versioned amendment of the frozen Session-039 v1 contracts.

Preserves suite/ files byte-for-byte; writes amended suite-v2/ once.
No model inference has used either version yet.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from . import curriculum as v1


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def build(split: str) -> dict:
    suite = copy.deepcopy(v1.build(split))
    suite["amendment_parent"] = "suite/MANIFEST.json (v1, immutable)"
    suite["amendment_reason"] = "v1 Prisma schema did not require status, but its UI/integration fixtures did"
    suite["amendment_version"] = 2
    for task in suite["tasks"]:
        task["contract_version"] = 2
        state = task["workflow"][0]
        if task["skill"] == "schema-relationship":
            task["requirements"].append(
                f"The child model also stores status String @default(\"{state}\"), persisted for UI/API workflows."
            )
        elif task["skill"] == "api-get-filter":
            task["requirements"].append("The listed records include the persisted status field.")
        elif task["skill"] == "api-post-validation":
            task["requirements"].append(f"Create status as {state!r} unless a valid workflow transition changes it later.")
        elif task["skill"] == "fullstack-integration":
            task["requirements"].append("The list displays the persisted status, not a fabricated client-only value.")
    return suite


def files() -> dict[str, bytes]:
    return {f"{split}.json": _encoded(build(split)) for split in v1.DOMAINS}


def manifest() -> dict:
    fs = files()
    return {"session": "039", "freeze_version": 2, "training_eligible": 0,
            "immutable_parent": "experiments/z039-generalization-learning/suite/MANIFEST.json",
            "versioned_reason": "Persisted workflow status must exist in schema and APIs; v1 remains preserved",
            "inference_on_any_version_at_freeze": 0,
            "splits": {split: {"task_count": len(v1.DOMAINS[split]) * len(v1.SKILLS),
                               "sha256": hashlib.sha256(fs[f"{split}.json"]).hexdigest()}
                       for split in v1.DOMAINS},
            "holdout_rule": "Never load holdout contracts or scenarios in model generation, tuning or feedback; only after final choices locked"}


def freeze(path: Path, *, check: bool) -> dict:
    contents = files()
    contents["MANIFEST.json"] = _encoded(manifest())
    if check:
        for name, data in contents.items():
            if not (path / name).is_file() or (path / name).read_bytes() != data:
                raise ValueError(f"Versioned suite drift: {name}")
    else:
        path.mkdir(parents=True, exist_ok=True)
        if any((path / name).exists() for name in contents):
            raise FileExistsError("Never overwrite a versioned frozen suite")
        for name, data in contents.items():
            (path / name).write_bytes(data)
    return manifest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=Path("experiments/z039-generalization-learning/suite-v2"))
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = p.parse_args()
    result = freeze(args.dir, check=args.check)
    print(json.dumps({"version": 2, "counts": {s: x["task_count"] for s,x in result["splits"].items()}, "training": False}))


if __name__ == "__main__":
    main()
