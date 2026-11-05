"""Trusted Python bridge. Invoke ONLY inside the restricted Session017 Docker.

Receives generated Python source as data over stdin. This worker never runs on
the model-generation host and never imports application code from the host.
"""
import ast
import json
from pathlib import Path
import sys


def main():
    if not Path("/.dockerenv").exists() or len(sys.argv) != 1:
        raise RuntimeError("Python-generated execution requires Docker")
    request = json.load(sys.stdin)
    source = request["source"]
    if not isinstance(source, str) or len(source) > 30000:
        raise ValueError("Invalid Python module")
    try:
        ast.parse(source)
    except (SyntaxError, ValueError) as error:
        print(json.dumps({"syntax_valid": False, "ok": False,
                          "error": f"SyntaxError: {error}"}))
        return
    try:
        namespace = {"__name__": "__session017_generated__"}
        exec(compile(source, "<generated-logic>", "exec"), namespace)
        transform = namespace.get("transform")
        if not callable(transform):
            raise TypeError("Python module did not define transform(payload)")
        outcome = transform(request["payload"])
        json.dumps(outcome, allow_nan=False)
        print(json.dumps({"syntax_valid": True, "ok": True, "value": outcome}, allow_nan=False))
    except BaseException as error:
        print(json.dumps({"syntax_valid": True, "ok": False,
                          "error": f"{type(error).__name__}: {error}"}))


if __name__ == "__main__":
    main()
