"""Run trusted oracle-validation controls for the Session-039 evaluators.

Two modes, both restricted to TRUSTED_TEACHER_CONTROL fixtures:

* Docker mode (default): stages exactly the same harness the real evaluator
  uses and runs the control inside the restricted container through
  ``docker_only``. This is the mode required before any Qwen candidate may
  be scored, and it is blocked whenever Docker is unavailable.
* ``--host-smoke`` mode: an explicitly disclosed trusted-code-only smoke
  test that runs the harness runner via the host Node binary against the
  trusted positive/negative controls. Model-generated code is NEVER run in
  this mode; the candidate path is always a trusted control file. The mode
  exists to catch harness logic defects (staging, Prisma wiring, import
  redirection, probe and verdict logic) that mocked unit tests cannot
  reach. It does not replace the Docker control run and produces no
  Docker-tier evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import docker_only, invariant_eval, route_eval, route_fixtures

CONTROLS = Path("experiments/z039-zai-execution/controls")
INVARIANT_TASK = "radiostation:state-invariant"
GET_TASK = "radiostation:api-get-filter"
POST_TASK = "radiostation:api-post-validation"


def _control_dir(repo: Path, name: str, staging_parent: Path) -> Path:
    directory = (repo / CONTROLS).resolve()
    control = (directory / name).resolve()
    if directory not in control.parents or not control.is_file() or control.is_symlink():
        raise ValueError("Control must be a regular file inside the controls directory")
    staging = staging_parent / f"{name.removesuffix('.ts')}-staged"
    staging.mkdir()
    shutil.copyfile(control, staging / "output.ts")
    return staging


def run_invariant_control(repo: Path, control_name: str, image: str | None,
                          *, host_smoke: bool = False) -> dict:
    repo = repo.resolve()
    with tempfile.TemporaryDirectory(prefix="s039-control-stage-") as stage:
        control_dir = _control_dir(repo, control_name, Path(stage))
        fixture = invariant_eval.task_fixture(repo, "dev", INVARIANT_TASK)
        trusted_runner = Path(__file__).resolve().parent / "harness" / "runner.mjs"
        with tempfile.TemporaryDirectory(prefix="s039-invariant-control-") as temp:
            harness = Path(temp)
            shutil.copyfile(trusted_runner, harness / "runner.mjs")
            (harness / "task.json").write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
            os.chmod(harness, 0o755)
            os.chmod(harness / "runner.mjs", 0o644)
            os.chmod(harness / "task.json", 0o644)
            if host_smoke:
                result = _host_smoke(harness, control_dir)
            else:
                if not image:
                    raise ValueError("Docker mode requires a pinned image digest")
                result = docker_only.run(image, control_dir, harness)
    return {"control": control_name, "task_id": INVARIANT_TASK, "kind": "invariant",
            "origin": "TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE", **result}


def run_route_control(repo: Path, control_name: str, task_id: str, image: str | None,
                      *, host_smoke: bool = False) -> dict:
    repo = repo.resolve()
    if task_id not in (GET_TASK, POST_TASK):
        raise ValueError("Route controls target the dev radiostation GET/POST contracts")
    with tempfile.TemporaryDirectory(prefix="s039-control-stage-") as stage:
        control_dir = _control_dir(repo, control_name, Path(stage))
        with tempfile.TemporaryDirectory(prefix="s039-route-control-") as temp:
            harness = Path(temp)
            if host_smoke:
                work = Path(temp) / "work"
                work.mkdir()
                client_import = str((work / "generated-client" / "index.js"))
                route_eval.stage_harness(repo, "dev", task_id, harness,
                                         work_dir=str(work), client_import=client_import)
                result = _host_smoke(harness, control_dir, work=str(work))
            else:
                if not image:
                    raise ValueError("Docker mode requires a pinned image digest")
                route_eval.stage_harness(repo, "dev", task_id, harness)
                result = docker_only.run_route(image, control_dir, harness)
    return {"control": control_name, "task_id": task_id,
            "kind": "api-get-filter" if task_id == GET_TASK else "api-post-validation",
            "origin": "TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE", **result}


def _host_smoke(harness: Path, control_dir: Path, *, work: str | None = None) -> dict:
    """Run the trusted runner with host Node; candidate path is ALWAYS a control."""
    env = dict(os.environ)
    env["S039_HARNESS"] = str(harness)
    env["S039_CANDIDATE"] = str(control_dir / "output.ts")
    if work:
        env["S039_WORK"] = work
    argv = ["node", "--experimental-strip-types", str(harness / "route_runner.mjs")] \
        if (harness / "route_runner.mjs").exists() \
        else ["node", "--experimental-strip-types", str(harness / "runner.mjs")]
    try:
        proc = subprocess.run(argv, text=True, capture_output=True, timeout=180, env=env,
                              cwd=str(harness), check=False)
    except subprocess.TimeoutExpired:
        return {"status": "HOST_SMOKE_TIMEOUT", "passed": False, "candidate_executed": False}
    except OSError as error:
        return {"status": "HOST_SMOKE_LAUNCH_FAILED", "passed": False,
                "candidate_executed": False, "error": str(error)[:200]}
    marker = docker_only.RESULT_MARKER
    lines = [line[len(marker):] for line in proc.stdout.splitlines() if line.startswith(marker)]
    record: dict = {"status": "HOST_SMOKE_EXECUTED_TRUSTED_CONTROL_ONLY", "candidate_executed": False,
                    "host_smoke": True, "returncode": proc.returncode,
                    "stderr_tail": proc.stderr.strip()[-400:]}
    if len(lines) != 1:
        record.update({"passed": False, "verdict": "NO_UNAMBIGUOUS_VERDICT", "stdout_tail": proc.stdout.strip()[-400:]})
        return record
    try:
        verdict = json.loads(lines[0])
    except json.JSONDecodeError:
        record.update({"passed": False, "verdict": "INVALID_VERDICT"})
        return record
    checks = verdict.get("checks") if isinstance(verdict, dict) else None
    valid = (isinstance(checks, list) and bool(checks)
             and all(isinstance(c, dict) and c.get("passed") is True for c in checks)
             and verdict.get("pass") is True)
    record.update({"passed": valid, "verdict": "CONTROL_PASS" if valid else "CONTROL_FAIL",
                   "reported_checks": len(checks) if isinstance(checks, list) else 0,
                   "checks": checks if isinstance(checks, list) else []})
    return record


CONTROL_MATRIX = {
    "invariant-positive-control.ts": ("invariant", INVARIANT_TASK, True),
    "invariant-negative-control.ts": ("invariant", INVARIANT_TASK, False),
    "invariant-invalid-ts-control.ts": ("invariant", INVARIANT_TASK, False),
    "invariant-missing-export-control.ts": ("invariant", INVARIANT_TASK, False),
    "get-positive-control.ts": ("route", GET_TASK, True),
    "get-negative-control.ts": ("route", GET_TASK, False),
    "get-partial-order-control.ts": ("route", GET_TASK, False),
    "get-async-hang-control.ts": ("route", GET_TASK, False),
    "post-positive-control.ts": ("route", POST_TASK, True),
    "post-negative-control.ts": ("route", POST_TASK, False),
}


def run_all(repo: Path, image: str | None, *, host_smoke: bool = False) -> dict:
    results = {}
    for name, (kind, task_id, expected_pass) in CONTROL_MATRIX.items():
        if kind == "invariant":
            outcome = run_invariant_control(repo, name, image, host_smoke=host_smoke)
        else:
            outcome = run_route_control(repo, name, task_id, image, host_smoke=host_smoke)
        outcome["expected_pass"] = expected_pass
        outcome["oracle_validated"] = outcome.get("passed") is expected_pass
        results[name] = outcome
    return {
        "mode": "HOST_SMOKE_TRUSTED_CONTROLS_ONLY" if host_smoke else "DOCKER_RESTRICTED",
        "model_generated_code_executed": False,
        "controls": results,
        "all_oracles_validated": all(x["oracle_validated"] for x in results.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--image", help="exact image@sha256 digest (Docker mode)")
    parser.add_argument("--host-smoke", action="store_true",
                        help="trusted-controls-only host Node smoke test (no model code)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.host_smoke and not args.image:
        parser.error("Docker mode requires --image; use --host-smoke for the trusted-only smoke test")
    result = run_all(args.repo, args.image, host_smoke=args.host_smoke)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "all_oracles_validated": result["all_oracles_validated"]}))
    return 0 if result["all_oracles_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
