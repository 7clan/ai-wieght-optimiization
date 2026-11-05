"""Per-case scored Python verifier. Must execute ONLY inside restricted Docker.

No EvalPlus/hiddens or reference solutions appear in this worker. It sees
only the candidate source and a bounded list of PUBLIC contract cases.
"""
from __future__ import annotations

import ast
import json
import multiprocessing as mp
from pathlib import Path
import sys


def _child(source, payload, queue):
    try:
        env = {"__name__": "__session018_generated__"}
        exec(compile(source, "<candidate>", "exec"), env)
        func = env.get("transform")
        if not callable(func):
            raise TypeError("Expected transform(payload)")
        result = func(payload)
        json.dumps(result, allow_nan=False)
        queue.put({"ok": True, "value": result})
    except BaseException as error:
        queue.put({"ok": False, "error": f"{type(error).__name__}: {error}"[:240]})


def _one(source, case):
    context = mp.get_context("fork")
    queue = context.Queue(maxsize=1)
    process = context.Process(target=_child,args=(source,case["payload"],queue))
    process.daemon = True
    process.start()
    process.join(2.0)
    if process.is_alive():
        process.terminate()
        process.join(0.5)
        if process.is_alive():
            process.kill()
            process.join(0.5)
        output = {"ok": False, "error": "TimeoutError: public case exceeded 2s"}
    else:
        try:
            output = queue.get(timeout=0.15)
        except Exception:
            output = {"ok": False, "error": "No worker result"}
    queue.close()
    if not output["ok"]:
        return {"passed": False, "error": output["error"]}
    actual, expected = output["value"], case["expected"]
    if json.dumps(actual,sort_keys=True,allow_nan=False) == json.dumps(
        expected,sort_keys=True,allow_nan=False):
        return {"passed": True, "error": None}
    return {"passed": False, "error":
            f"Expected {json.dumps(expected,sort_keys=True)}, got {json.dumps(actual,sort_keys=True)}"[:300]}


def main():
    if not Path("/.dockerenv").exists() or len(sys.argv) != 3:
        raise RuntimeError("Do not execute generated code outside Docker")
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    source, cases = request["source"], request["cases"]
    if (not isinstance(source,str) or len(source)>30000
        or not isinstance(cases,list) or not 1<=len(cases)<=8):
        raise ValueError("Invalid public verifier request")
    try:
        ast.parse(source)
    except (SyntaxError, ValueError, MemoryError) as error:
        result = {"syntax_valid": False, "passed_count": 0,
                  "cases_total": len(cases), "passed_all": False,
                  "failures": [{"index": i, "error": f"SyntaxError: {error}"[:240]}
                               for i in range(len(cases))]}
    else:
        checked = [_one(source, case) for case in cases]
        passed = sum(bool(c["passed"]) for c in checked)
        result = {"syntax_valid": True, "passed_count": passed,
                  "cases_total": len(cases), "passed_all": passed==len(cases),
                  "failures": [{"index": i, "error": x["error"]}
                               for i,x in enumerate(checked) if not x["passed"]]}
    result["task_id"] = request["task_id"]
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
