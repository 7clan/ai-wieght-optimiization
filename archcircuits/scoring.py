"""Answer extraction, normalization and scoring for ArchBench.

Short-answer scoring avoids executing model-generated code entirely: the gold
answers are deterministic values computed from reference snippets authored by
us.  Normalization handles the common surface forms a base model emits
(bare values, 'x = 16', trailing periods, JS-style literals).
"""

from __future__ import annotations

import ast
import re


def extract_answer(generated: str) -> str:
    """Take the text following 'A:' up to the first stop boundary."""
    text = generated.strip()
    # cut at a new question, a closing fence, or a blank line
    for stop in ("\nQ:", "\n```", "\n\n", "\n#", "\n//"):
        idx = text.find(stop)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _js_object_literal(text: str):
    """Quote bare JS object keys so '{ b: 2 }' parses as a Python literal."""
    cleaned = text.strip().rstrip(";")
    return re.sub(r"([{,]\s*)([A-Za-z_][\w]*)\s*:", lambda m: f'{m.group(1)}"{m.group(2)}":', cleaned)


def _try_literal(text: str):
    """Parse Python or JS-ish literals; returns (value, ok)."""
    cleaned = text.strip().rstrip(";")
    # strip a leading 'return' that the model may prepend
    if cleaned.startswith("return "):
        cleaned = cleaned[len("return "):].strip()
    # JS literal tweaks: true/false/null -> Python
    js = re.sub(r"\btrue\b", "True", cleaned)
    js = re.sub(r"\bfalse\b", "False", js)
    js = re.sub(r"\bnull\b", "None", js)
    js_obj = _js_object_literal(js)
    for candidate in (cleaned, js, js_obj):
        try:
            return ast.literal_eval(candidate), True
        except (ValueError, SyntaxError):
            continue
    return None, False


def _strip_type_hints(sig: str) -> str:
    """'def f(a: dict, b: str) -> dict:' -> 'def f(a, b)'."""
    s = sig.strip().rstrip(":").strip()
    s = re.sub(r"\)\s*->\s*[^:]+$", ")", s)
    s = re.sub(r":\s*[A-Za-z_][\w\.\[\], ]*(?=,|\)|$)", "", s)
    s = re.sub(r"=\s*[^,)]+", "", s)
    return re.sub(r"\s+", "", s)


def normalize(text: str, kind: str = "generic") -> str:
    t = text.strip().strip("`").strip()
    t = t.rstrip(".;")
    if kind == "order":
        return re.sub(r"[\s,>]+", "", t).lower()
    if kind == "identifier":
        m = re.search(r"[A-Za-z_][\w.]*", t)
        return (m.group(0) if m else t).strip('"\'')
    if kind == "signature":
        return _strip_type_hints(t)
    # generic: strip one layer of matching quotes if present
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        t = t[1:-1]
    return t.strip()


_ANSWER_KIND = {
    "identifier": ("binding", "rename", "field"),
}


def answer_kind(task: dict) -> str:
    sub = task.get("subcategory", "")
    if task["category"] == "XCOM" or sub in _ANSWER_KIND.get("identifier", ()):
        return "identifier"
    if sub == "signature":
        return "signature"
    if "order" in task.get("question", "").lower() or "logged order" in task["question"].lower():
        return "order"
    return "generic"


def score_answer(task: dict, prediction: str) -> dict:
    """Return {correct, normalized_prediction, normalized_gold, method}."""
    gold = task["gold"]
    kind = answer_kind(task)
    p_norm = normalize(prediction, kind)
    g_norm = normalize(gold, kind)

    # 1) literal comparison (numbers, lists, dicts, strings)
    p_val, p_ok = _try_literal(prediction)
    g_val, g_ok = _try_literal(gold)
    if p_ok and g_ok:
        try:
            if _equal_values(p_val, g_val):
                return {"correct": True, "normalized_prediction": p_norm,
                        "normalized_gold": g_norm, "method": "literal"}
        except Exception:
            pass

    # 2) identifier / order / signature exact match after normalization
    if p_norm == g_norm and p_norm:
        return {"correct": True, "normalized_prediction": p_norm,
                "normalized_gold": g_norm, "method": kind}

    # 3) generic contains-match for quoted strings the model may embed
    if g_norm and g_norm in p_norm and len(p_norm) <= len(g_norm) + 6:
        return {"correct": True, "normalized_prediction": p_norm,
                "normalized_gold": g_norm, "method": "contains"}

    return {"correct": False, "normalized_prediction": p_norm,
            "normalized_gold": g_norm, "method": "mismatch"}


def _equal_values(a, b) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal_values(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a.keys()) == set(b.keys()) and all(_equal_values(a[k], b[k]) for k in a)
    return a == b
