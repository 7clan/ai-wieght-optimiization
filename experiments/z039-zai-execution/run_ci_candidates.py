"""Run every staged Session-039 candidate through the Docker-only evaluators.

Intended for the approved GitHub Actions Docker job (see
.github/workflows/s039-docker-eval.yml) or any user-provided
Docker-capable environment. Requires the exact pinned image digest.
Candidates are discovered under
experiments/z039-generalization-learning/candidates/<task-id>/output.ts;
the evaluator is chosen from the frozen v2 contract skill. Holdout tasks
are refused. Every verdict is fail-closed; this script never fabricates a
result and never executes candidate code outside the restricted container.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from archagent.s039 import docker_only, invariant_eval, route_eval, scenarios  # noqa: E402

CANDIDATES = Path("experiments/z039-generalization-learning/candidates")


def discover(repo: Path) -> list[tuple[str, str, Path]]:
    root = (repo / CANDIDATES).resolve()
    if not root.is_dir():
        return []
    found = []
    for task_dir in sorted(root.iterdir()):
        if not task_dir.is_dir() or "__" not in task_dir.name:
            continue
        task_id = task_dir.name.replace("__", ":", 1)
        split = skill = None
        for candidate_split in ("train", "dev"):
            try:
                suite = scenarios.load_split(repo, candidate_split, suite_version=2)
            except (ValueError, PermissionError):
                continue
            for task in suite["tasks"]:
                if task["id"] == task_id:
                    split, skill = candidate_split, task["skill"]
                    break
            if split:
                break
        if split is None or skill is None:
            continue  # unknown or holdout task: refuse silently, fail closed
        found.append((split, task_id, task_dir))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--image", required=True, help="exact image@sha256 digest")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if docker_only.IMAGE_RE.fullmatch(args.image) is None:
        parser.error("--image must be an exact image@sha256:<64 hex> digest")

    results = []
    for split, task_id, task_dir in discover(args.repo):
        try:
            if task_id.endswith(":state-invariant"):
                outcome = invariant_eval.evaluate(args.repo, split, task_id, task_dir, args.image)
            else:
                outcome = route_eval.evaluate(args.repo, split, task_id, task_dir, args.image)
        except Exception as error:  # fail closed, never crash the batch
            outcome = {"task_id": task_id, "split": split, "status": "EVALUATOR_ERROR",
                       "passed": False, "error": str(error)[:200]}
        results.append(outcome)

    passed = sum(1 for r in results if r.get("passed") is True)
    report = {
        "image": args.image,
        "candidates_discovered": len(results),
        "behavior_passes": passed,
        "model_weight_change": False,
        "holdout_opened": False,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
