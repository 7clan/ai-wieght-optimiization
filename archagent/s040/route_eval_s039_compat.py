"""Session-039 evaluator compatibility shims for the Session-040 tier.

The trusted s039 invariant and route runners are env-parameterized
(S039_HARNESS / S039_CANDIDATE / S039_WORK) and emit their own
S039-RESULT marker, so they execute unchanged inside the s040 restricted
tier (compat mode of archagent.s040.exec). The staging logic is reused
verbatim from the s039 modules; only the execution backend differs
(unshare local tier or Docker, never bare host).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile

from archagent.s039 import invariant_eval, route_eval
from archagent.s040 import exec as s040exec


def _validated_candidate(repo: Path, candidate_dir: Path, filename: str) -> Path:
    candidate_dir = candidate_dir.resolve(strict=True)
    experiments_root = (repo / "experiments").resolve()
    import tempfile as _tempfile
    tmp_root = Path(_tempfile.gettempdir()).resolve()
    if experiments_root not in candidate_dir.parents and tmp_root not in candidate_dir.parents:
        raise ValueError("Candidate must live inside the repository experiments tree "
                         "or a controller-created OS temp directory")
    files = list(candidate_dir.iterdir())
    if (len(files) != 1 or files[0].name != filename
            or files[0].is_symlink() or not files[0].is_file()):
        raise FileNotFoundError(f"Candidate directory must contain {filename}")
    return candidate_dir


def evaluate_invariant(repo: Path, split: str, task_id: str, candidate_dir: Path, *,
                       backend: str = "auto", image: str | None = None) -> dict:
    if split not in ("train", "dev"):
        raise PermissionError("Final holdout is sealed from this evaluator")
    repo = repo.resolve()
    candidate_dir = _validated_candidate(repo, candidate_dir, "output.ts")
    with tempfile.TemporaryDirectory(prefix="s040-inv-harness-") as temp:
        harness = Path(temp)
        fixture = invariant_eval.task_fixture(repo, split, task_id)
        shutil.copyfile(Path(invariant_eval.__file__).parent / "harness" / "runner.mjs",
                        harness / "runner.mjs")
        (harness / "task.json").write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        result = s040exec.run(candidate_dir, harness, s040exec.DEFAULT_EVAL_DEPS,
                              runner="runner.mjs", backend=backend, image=image)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            "case_count": len(fixture["cases"]), **result, "model_weight_change": False}


def evaluate_route(repo: Path, split: str, task_id: str, candidate_dir: Path, *,
                   backend: str = "auto", image: str | None = None) -> dict:
    if split not in ("train", "dev"):
        raise PermissionError("Final holdout is sealed from this evaluator")
    repo = repo.resolve()
    candidate_dir = _validated_candidate(repo, candidate_dir, "output.ts")
    with tempfile.TemporaryDirectory(prefix="s040-route-harness-") as temp:
        harness = Path(temp)
        spec = route_eval.stage_harness(repo, split, task_id, harness)
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        result = s040exec.run(candidate_dir, harness, s040exec.DEFAULT_EVAL_DEPS,
                              runner="route_runner.mjs", backend=backend, image=image)
    return {"task_id": task_id, "split": split, "suite_version": 2,
            "route_path": spec["route_path"], "case_count": len(spec["cases"]),
            "case_amendment": spec.get("case_amendment"),
            **result, "model_weight_change": False}
