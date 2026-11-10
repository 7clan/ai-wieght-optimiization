"""Run the trusted control matrix for the Session-040 evaluators.

Every control is TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE. The matrix proves
the two new evaluators (react-interaction, fullstack-integration) accept
faithful implementations and reject known-bad ones (ignored filter wiring,
missing controls, unlabeled inputs, fabricated success, wrong endpoints,
hangs, invalid TypeScript, missing exports) inside the SAME restricted
execution tier used for model-generated candidates. This is the gate that
must pass before any Qwen candidate may be scored by these evaluators.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import time

from archagent.s040 import exec as s040exec
from archagent.s040 import integration_eval, react_eval

CONTROLS = Path("experiments/z040-autonomous-fullstack/controls")

REACT_TASK = "radiostation:react-interaction"
INTEGRATION_TASK = "radiostation:fullstack-integration"

CONTROL_MATRIX = {
    # react-interaction (8)
    "react-positive-control.tsx": ("react", True),
    "react-search-ignored-control.tsx": ("react", False),
    "react-status-ignored-control.tsx": ("react", False),
    "react-no-clear-control.tsx": ("react", False),
    "react-unlabeled-control.tsx": ("react", False),
    "react-hang-control.tsx": ("react", False),
    "react-invalid-ts-control.tsx": ("react", False),
    "react-missing-export-control.tsx": ("react", False),
    # fullstack-integration (7)
    "integration-positive-control.tsx": ("integration", True),
    "integration-no-error-display.tsx": ("integration", False),
    "integration-phantom.tsx": ("integration", False),
    "integration-wrong-path.tsx": ("integration", False),
    "integration-hang-control.tsx": ("integration", False),
    "integration-invalid-ts-control.tsx": ("integration", False),
    "integration-missing-export-control.tsx": ("integration", False),
}


def run_all(repo: Path, *, backend: str = "auto") -> dict:
    repo = repo.resolve()
    controls_dir = (repo / CONTROLS).resolve()
    results = {}
    for name, (kind, expected_pass) in CONTROL_MATRIX.items():
        with tempfile.TemporaryDirectory(prefix=f"s040-ctl-{kind}-") as tmp:
            tmp = Path(tmp)
            cand = tmp / "c"
            cand.mkdir()
            shutil.copyfile(controls_dir / name, cand / "output.tsx")
            harness = tmp / "h"
            harness.mkdir()
            if kind == "react":
                react_eval.stage_harness(repo, "dev", REACT_TASK, harness)
                outcome = s040exec.run(cand, harness, s040exec.DEFAULT_EVAL_DEPS,
                                       runner="react_runner.mjs", tier="react", backend=backend)
            else:
                integration_eval.stage_harness(repo, "dev", INTEGRATION_TASK, harness)
                outcome = s040exec.run(cand, harness, s040exec.DEFAULT_EVAL_DEPS,
                                       runner="integration_runner.mjs", tier="integration", backend=backend)
        outcome["expected_pass"] = expected_pass
        outcome["oracle_validated"] = outcome.get("passed") is expected_pass
        results[name] = outcome
    return {
        "mode": "RESTRICTED_TIER_TRUSTED_CONTROLS_ONLY",
        "backend": backend,
        "model_generated_code_executed": False,
        "origin": "TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE",
        "controls": results,
        "all_oracles_validated": all(x["oracle_validated"] for x in results.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--backend", choices=["auto", "docker", "unshare"], default="auto")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    t0 = time.time()
    result = run_all(args.repo, backend=args.backend)
    result["elapsed_seconds"] = round(time.time() - t0, 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": result["mode"], "backend": result["backend"],
                      "all_oracles_validated": result["all_oracles_validated"],
                      "elapsed_seconds": result["elapsed_seconds"]}))
    return 0 if result["all_oracles_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
