"""Trusted evaluator entry point, invoked ONLY in a restricted Docker container.

Runs EvalPlus's own MBPP+ oracle and check_correctness on preselected problems.
The input pickle is created by the trusted host runner, not by model output.
This module must never be launched directly on an unsandboxed host.
"""

from __future__ import annotations

import ast
import copy
import json
from multiprocessing import get_context
from pathlib import Path
import pickle
import sys


def _probe_solution(solution, entry_point, args, result_queue):
    """One diagnostic call in a child of the already isolated container."""
    try:
        namespace = {"__name__": "__main__"}
        exec(solution, namespace)
        namespace[entry_point](*copy.deepcopy(args))
    except BaseException as exc:  # Best-effort *observed* exception categorization.
        result_queue.put(("exception", type(exc).__name__))
    else:
        result_queue.put(("returned", None))


def probe_failure(solution, problem, args):
    context = get_context("fork")
    queue = context.Queue(maxsize=1)
    proc = context.Process(target=_probe_solution, args=(solution, problem["entry_point"], args, queue))
    proc.daemon = True
    proc.start()
    proc.join(3)
    if proc.is_alive():
        proc.terminate()
        proc.join(2)
        if proc.is_alive():
            proc.kill()
            proc.join(2)
        outcome = ("timeout", None)
    else:
        try:
            outcome = queue.get(timeout=0.3)
        except Exception:
            outcome = ("unknown", None)
    queue.close()
    return outcome


def label_failure(problem, solution, evaluation):
    """Conservative, observable buckets; no asserted diagnosis without a probe."""
    from evalplus.eval import PASS

    base_status, base_details = evaluation["base"]
    plus_status, plus_details = evaluation["plus"]
    if base_status == PASS and plus_status == PASS:
        return "passed", None, None
    if base_status != PASS:
        name = "base"
        flags = base_details
    else:
        name = "plus"
        flags = plus_details
    inputs = problem[f"{name}_input"]
    if not flags or len(flags) > len(inputs):
        return "unclassified_logic_gap", None, None
    failed = next((i for i, value in enumerate(flags) if not value), None)
    if failed is None or failed >= len(inputs):
        return "unclassified_logic_gap", None, None
    outcome, exception = probe_failure(solution, problem, inputs[failed])
    if outcome == "exception":
        return "unhandled_exception", name, exception
    if outcome != "returned":
        return "unclassified_logic_gap", name, None
    if name == "plus":
        # More complex additional inputs; boundary/edge-case *proxy*, not proof.
        return "boundary_edge_case", name, None
    return "assertion_error", name, None


def evaluate(items):
    from evalplus.eval import PASS
    from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS
    from evalplus.evaluate import check_correctness
    from evalplus.gen.util import trusted_exec

    if not 1 <= len(items) <= 5:
        raise ValueError("Docker evaluator accepts chunks of 1..5 selected tasks")
    records = []
    for item in items:
        problem, solution = item["problem"], item["solution"]
        task_id = problem["task_id"]
        ast_valid = item["syntax_valid"]
        if not isinstance(solution, str) or len(solution) > 50000:
            raise ValueError("Invalid generated solution length")
        try:
            ast.parse(solution)
            syntax_validated = True
        except (SyntaxError, ValueError, MemoryError):
            syntax_validated = False
        if syntax_validated != ast_valid:
            raise ValueError("Host/container syntax checks disagree")
        if not ast_valid:
            records.append({"task_id": task_id, "syntax_valid": False,
                            "base_pass": False, "plus_pass": False,
                            "base_status": "not_run_syntax_invalid",
                            "plus_status": "not_run_syntax_invalid",
                            "failure_bin": "syntax_invalid", "diagnostic_source": None,
                            "observed_exception": None})
            continue
        canonical = problem["prompt"] + problem["canonical_solution"]
        not_none = problem["entry_point"] in MBPP_OUTPUT_NOT_NONE_TASKS
        base_expected, base_times = trusted_exec(
            canonical, problem["base_input"], problem["entry_point"],
            record_time=True, output_not_none=not_none)
        plus_expected, plus_times = trusted_exec(
            canonical, problem["plus_input"], problem["entry_point"],
            record_time=True, output_not_none=not_none)
        oracle = {"base": base_expected, "base_time": base_times,
                  "plus": plus_expected, "plus_time": plus_times}
        outcome = check_correctness(
            "mbpp", 0, problem, solution, oracle, base_only=False,
            fast_check=False, identifier=task_id)
        base, plus = outcome["base"][0] == PASS, outcome["plus"][0] == PASS
        label, origin, exception = label_failure(problem, solution, outcome)
        records.append({
            "task_id": task_id, "syntax_valid": ast_valid,
            "base_pass": base, "plus_pass": base and plus,
            "base_status": str(outcome["base"][0]),
            "plus_status": str(outcome["plus"][0]),
            "base_test_count": len(problem["base_input"]),
            "plus_test_count": len(problem["plus_input"]),
            "failure_bin": label, "diagnostic_source": origin,
            "observed_exception": exception,
        })
    return records


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Expected input pickle and output JSON paths")
    # This is a defense-in-depth check. Docker isolation itself is applied by
    # the caller: --network none, --read-only, unprivileged user and cgroup caps.
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Refusing to execute MBPP-generated code outside Docker")
    with open(sys.argv[1], "rb") as handle:
        items = pickle.load(handle)
    results = evaluate(items)
    Path(sys.argv[2]).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
