"""Stage Session-039 invariant test cases for a Docker-only evaluator.

No source output is read or executed in Python. Requires a vetted image
already available locally and pinned by image@sha256 digest.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import docker_only, scenarios


def task_fixture(repo: Path, split: str, task_id: str) -> dict:
    suite = scenarios.load_split(repo, split, suite_version=2)
    entries = [task for task in suite["tasks"] if task["id"] == task_id]
    if len(entries) != 1 or entries[0]["skill"] != "state-invariant":
        raise ValueError("Expected one frozen state-invariant task in train/dev")
    entry = entries[0]
    cases = scenarios.oracle_cases(entry)
    if len(cases) < 6 or any(not isinstance(c["expected"], bool) for c in cases):
        raise ValueError("Behavior cases were not complete")
    return {"task_id": task_id, "export_name": f"canAdvance{entry['entities']['child']}", "cases": cases}


def evaluate(repo: Path, split: str, task_id: str, candidate_dir: Path, image: str) -> dict:
    if split not in ("train", "dev"):
        raise PermissionError("Final holdout is sealed from this evaluator")
    repo = repo.resolve()
    candidate_dir = candidate_dir.resolve(strict=True)
    candidate_root = (repo / "experiments/z039-generalization-learning/candidates").resolve()
    expected_dir = candidate_root / task_id.replace(":", "__")
    if candidate_dir != expected_dir or not candidate_dir.is_dir():
        raise ValueError("Candidate must be inside its dedicated Session-039 task directory")
    files = list(candidate_dir.iterdir())
    if len(files) != 1 or files[0].name != "output.ts" or files[0].is_symlink() or not files[0].is_file():
        raise FileNotFoundError("Candidate directory must contain output.ts")
    fixture = task_fixture(repo, split, task_id)
    trusted_runner = Path(__file__).resolve().parent / "harness" / "runner.mjs"
    with tempfile.TemporaryDirectory(prefix="s039-invariant-harness-") as temp:
        harness = Path(temp)
        shutil.copyfile(trusted_runner, harness / "runner.mjs")
        (harness / "task.json").write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
        # TemporaryDirectory defaults to 0700; the non-root Docker UID needs
        # read/execute access to the bind-mounted (read-only) fixture folder.
        os.chmod(harness, 0o755)
        os.chmod(harness / "runner.mjs", 0o644)
        os.chmod(harness / "task.json", 0o644)
        result = docker_only.run(image, candidate_dir, harness)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            **result, "model_weight_change": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--split", choices=["train", "dev"], required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--image", required=True, help="exact image@sha256 digest")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.repo, args.split, args.task_id, args.candidate_dir, args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
