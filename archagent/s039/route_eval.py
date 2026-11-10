"""Stage Session-039 GET/POST route cases for the Docker-only evaluator.

No model-generated source is read, modified or executed here. The trusted
fixtures are derived from the frozen v2 contracts and scenario plans, staged
into a temporary harness directory and bind-mounted read-only into the
restricted container. Requires a vetted Node 24 + Prisma image already
available locally and pinned by image@sha256 digest.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import docker_only, route_fixtures


def stage_harness(repo: Path, split: str, task_id: str, harness: Path,
                  *, work_dir: str = "/work",
                  client_import: str = route_fixtures.DEFAULT_CLIENT_IMPORT) -> dict:
    """Stage the trusted route-evaluation harness into ``harness``."""
    spec = route_fixtures.task_spec(repo, split, task_id)
    suite = route_fixtures.scenarios.load_split(repo, split, suite_version=2)
    entry = next(task for task in suite["tasks"] if task["id"] == task_id)
    trusted_runner = Path(__file__).resolve().parent / "harness" / "route_runner.mjs"
    shutil.copyfile(trusted_runner, harness / "route_runner.mjs")
    (harness / "task.json").write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    (harness / "schema.prisma").write_text(
        route_fixtures.prisma_schema(entry, work_dir=work_dir), encoding="utf-8")
    (harness / "db.ts").write_text(
        route_fixtures.db_client_ts(client_import=client_import), encoding="utf-8")
    (harness / "fixture.mjs").write_text(
        route_fixtures.fixture_mjs(entry, client_import=client_import), encoding="utf-8")
    (harness / "seed.mjs").write_text(
        route_fixtures.seed_mjs(client_import=client_import), encoding="utf-8")
    return spec


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
    with tempfile.TemporaryDirectory(prefix="s039-route-harness-") as temp:
        harness = Path(temp)
        spec = stage_harness(repo, split, task_id, harness)
        # TemporaryDirectory defaults to 0700; the non-root Docker UID needs
        # read/execute access to the bind-mounted (read-only) fixture folder.
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        result = docker_only.run_route(image, candidate_dir, harness)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            "route_path": spec["route_path"], "case_count": len(spec["cases"]),
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
