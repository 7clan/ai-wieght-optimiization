"""Execute ONLY prompt-provided MBPP public assertions inside isolated Docker.

Unlike the final EvalPlus evaluator, this worker NEVER loads canonical solutions,
plus inputs or expanded test oracles. It only sees original MBPP test_list
assertions, which are public examples of the task specification.
"""
from __future__ import annotations

import ast
import json
import multiprocessing as mp
from pathlib import Path
import pickle
import sys


def _execute(solution, tests, queue):
    try:
        env = {"__name__": "__main__"}
        exec(compile(solution, "<candidate>", "exec"), env)
        for test in tests:
            exec(compile(test, "<public-test>", "exec"), env)
    except BaseException as exc:
        queue.put((False, type(exc).__name__, str(exc)[:240]))
    else:
        queue.put((True, None, None))


def check(item):
    code = item["solution"]
    tests = item["public_tests"]
    if not isinstance(code, str) or len(code) > 50000:
        raise ValueError("Malformed candidate")
    if not isinstance(tests, list) or not 1 <= len(tests) <= 10 or not all(
        isinstance(t, str) and len(t) < 5000 for t in tests
    ):
        raise ValueError("Malformed public tests")
    try:
        ast.parse(code)
    except (SyntaxError, ValueError, MemoryError):
        return {"task_id": item["task_id"], "syntax_valid": False,
                "passed": False, "failure_bin": "syntax_invalid", "error": "SyntaxError"}
    queue = mp.get_context("fork").Queue(maxsize=1)
    child = mp.get_context("fork").Process(target=_execute, args=(code, tests, queue))
    child.daemon = True
    child.start()
    child.join(4)
    if child.is_alive():
        child.terminate()
        child.join(2)
        if child.is_alive():
            child.kill()
            child.join(2)
        result = (False, "TimeoutError", "Public test timed out")
    else:
        try:
            result = queue.get(timeout=0.1)
        except Exception:
            result = (False, "RuntimeError", "No public test result")
    queue.close()
    good, kind, msg = result
    return {"task_id": item["task_id"], "syntax_valid": True,
            "passed": good, "failure_bin": "passed" if good else
            ("assertion_error" if kind == "AssertionError" else "unhandled_exception"),
            "error": (kind + ": " + msg) if kind else None}


def main():
    if len(sys.argv) != 3 or not Path("/.dockerenv").exists():
        raise RuntimeError("The public evaluator must run only inside Docker")
    with open(sys.argv[1], "rb") as handle:
        items = pickle.load(handle)
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError("Expected at most five tested candidates")
    result = [check(item) for item in items]
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
