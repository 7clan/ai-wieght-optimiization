"""Stage and run Session-040 fullstack-integration evaluations.

Controller-side trusted code: stages the frozen task spec, the trusted
Prisma fixture and the trusted reference route, then executes the candidate
component inside the restricted tier via ``archagent.s040.exec``. The
candidate's fetch calls are routed in-process to the reference route backed
by the real seeded SQLite database (see integration_runner.mjs). The
candidate file is never modified; the holdout is refused.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from archagent.s039 import route_fixtures
from archagent.s040 import exec as s040exec
from archagent.s040 import integration_fixtures

CANDIDATE_ROOT = Path("experiments/z039-generalization-learning/candidates")
DEFAULT_CLIENT_IMPORT = route_fixtures.DEFAULT_CLIENT_IMPORT


def stage_harness(repo: Path, split: str, task_id: str, harness: Path,
                  *, client_import: str = DEFAULT_CLIENT_IMPORT) -> dict:
    spec = integration_fixtures.task_spec(repo, split, task_id)
    suite = route_fixtures.scenarios.load_split(repo, split, suite_version=2)
    entry = next(task for task in suite["tasks"] if task["id"] == task_id)
    trusted_runner = Path(__file__).resolve().parent / "harness" / "integration_runner.mjs"
    shutil.copyfile(trusted_runner, harness / "integration_runner.mjs")
    (harness / "task.json").write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    (harness / "schema.prisma").write_text(
        route_fixtures.prisma_schema(entry, work_dir="/work"), encoding="utf-8")
    (harness / "db.ts").write_text(
        route_fixtures.db_client_ts(client_import=client_import), encoding="utf-8")
    (harness / "fixture.mjs").write_text(
        route_fixtures.fixture_mjs(entry, client_import=client_import), encoding="utf-8")
    (harness / "seed.mjs").write_text(
        route_fixtures.seed_mjs(client_import=client_import), encoding="utf-8")
    (harness / "route.mjs").write_text(
        integration_fixtures.reference_route_mjs(spec, client_import=client_import), encoding="utf-8")
    return spec


def evaluate(repo: Path, split: str, task_id: str, candidate_dir: Path, *,
             backend: str = "auto", image: str | None = None) -> dict:
    if split not in ("train", "dev"):
        raise PermissionError("Final holdout is sealed from this evaluator")
    repo = repo.resolve()
    candidate_dir = candidate_dir.resolve(strict=True)
    expected_dir = (repo / CANDIDATE_ROOT / task_id.replace(":", "__")).resolve()
    if candidate_dir != expected_dir or not candidate_dir.is_dir():
        raise ValueError("Candidate must be inside its dedicated Session-039 task directory")
    files = list(candidate_dir.iterdir())
    if (len(files) != 1 or files[0].name != "output.tsx"
            or files[0].is_symlink() or not files[0].is_file()):
        raise FileNotFoundError("Candidate directory must contain output.tsx")
    with tempfile.TemporaryDirectory(prefix="s040-int-harness-") as temp:
        harness = Path(temp)
        spec = stage_harness(repo, split, task_id, harness)
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        result = s040exec.run(candidate_dir, harness, s040exec.DEFAULT_EVAL_DEPS,
                              runner="integration_runner.mjs", tier="integration",
                              backend=backend, image=image)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            "route_path": spec["route_path"], "case_count": len(spec["cases"]),
            **result, "model_weight_change": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--split", choices=["train", "dev"], required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=["auto", "docker", "unshare"], default="auto")
    parser.add_argument("--image", help="exact image@sha256 digest (Docker backend)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.repo, args.split, args.task_id, args.candidate_dir,
                      backend=args.backend, image=args.image)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
