"""Stage and run Session-040 react-interaction evaluations.

Controller-side trusted code: derives the frozen task spec, stages the
harness, and executes the candidate inside the restricted tier via
``archagent.s040.exec`` (Docker in approved CI; the disclosed unshare
namespace tier locally). The candidate file is never modified; holdout is
refused.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from archagent.s040 import exec as s040exec
from archagent.s040 import react_fixtures

CANDIDATE_ROOT = Path("experiments/z039-generalization-learning/candidates")


def stage_harness(repo: Path, split: str, task_id: str, harness: Path) -> dict:
    spec = react_fixtures.task_spec(repo, split, task_id)
    trusted_runner = Path(__file__).resolve().parent / "harness" / "react_runner.mjs"
    shutil.copyfile(trusted_runner, harness / "react_runner.mjs")
    (harness / "task.json").write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    return spec


def evaluate(repo: Path, split: str, task_id: str, candidate_dir: Path, *,
             backend: str = "auto", image: str | None = None) -> dict:
    if split not in ("train", "dev"):
        raise PermissionError("Final holdout is sealed from this evaluator")
    repo = repo.resolve()
    candidate_dir = candidate_dir.resolve(strict=True)
    experiments_root = (repo / "experiments").resolve()
    import tempfile as _tempfile
    tmp_root = Path(_tempfile.gettempdir()).resolve()
    if experiments_root not in candidate_dir.parents and tmp_root not in candidate_dir.parents:
        raise ValueError("Candidate must live inside the repository experiments tree "
                         "or a controller-created OS temp directory")
    files = list(candidate_dir.iterdir())
    if (len(files) != 1 or files[0].name != "output.tsx"
            or files[0].is_symlink() or not files[0].is_file()):
        raise FileNotFoundError("Candidate directory must contain output.tsx")
    with tempfile.TemporaryDirectory(prefix="s040-react-harness-") as temp:
        harness = Path(temp)
        spec = stage_harness(repo, split, task_id, harness)
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        result = s040exec.run(candidate_dir, harness, s040exec.DEFAULT_EVAL_DEPS,
                              runner="react_runner.mjs", tier="react",
                              backend=backend, image=image)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            "case_count": len(spec["cases"]), **result, "model_weight_change": False}


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
