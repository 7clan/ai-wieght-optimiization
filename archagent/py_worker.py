"""Execute one Qwen-produced Python function for the archagent evaluator.

Isolated `python3 -I -B` subprocess (no site imports, no bytecode writes,
no network).  Docker is unavailable in the recycled sandbox; this is the
disclosed local mode with the same isolation properties the Docker image
provides (unprivileged, isolated interpreter, resource limits).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def main() -> None:
    import os
    if not Path("/.dockerenv").is_file() and os.environ.get(
            "ARCHAGENT_LOCAL_EVAL") != "1":
        raise RuntimeError(
            "Generated Python must run in Docker or disclosed local mode")
    request = json.load(sys.stdin)
    source = request["source"]
    fn_name = request.get("fn", "summarize")
    if not isinstance(source, str) or len(source) > 40000:
        print(json.dumps({"ok": False, "syntax_valid": False,
                          "error": "invalid code length"}))
        return
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        print(json.dumps({"ok": False, "syntax_valid": False,
                          "error": str(exc)}))
        return
    try:
        namespace = {"__name__": "__qwen_generated__"}
        exec(compile(tree, "<generated-python>", "exec"), namespace)
        fn = namespace[fn_name]
        if "cases" in request:
            results = []
            for case in request["cases"]:
                try:
                    got = fn(case["payload"])
                    results.append({"ok": got == case["expected"],
                                    "got": got, "expected": case["expected"]})
                except BaseException as exc:
                    import traceback
                    tb = traceback.extract_tb(exc.__traceback__)
                    line = tb[-1].lineno if tb else None
                    results.append({"ok": False, "got": None,
                                    "expected": case["expected"],
                                    "error": f"{type(exc).__name__}: {exc}",
                                    "line": line})
            print(json.dumps({"ok": all(r["ok"] for r in results),
                              "syntax_valid": True, "results": results}))
        else:
            value = fn(request["payload"])
            print(json.dumps({"ok": True, "syntax_valid": True, "value": value}))
    except BaseException as exc:
        print(json.dumps({"ok": False, "syntax_valid": True,
                          "error": f"{type(exc).__name__}: {exc}"}))


if __name__ == "__main__":
    main()
