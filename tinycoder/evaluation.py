"""Conservative static code checks; generated programs are never executed."""

from __future__ import annotations

import ast
import re


def extract_python(answer: str) -> str:
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", answer, flags=re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else answer).strip()


def static_check(answer: str, expected_function: str) -> dict:
    source = extract_python(answer)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"syntax_valid": False, "function_found": False, "static_pass": False}
    present = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == expected_function
                  for node in tree.body)
    return {"syntax_valid": True, "function_found": present, "static_pass": present}

