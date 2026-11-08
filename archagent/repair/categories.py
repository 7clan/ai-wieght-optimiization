"""SESSION 036 — PHASE 2 (TRUSTED-SCAFFOLD).

Error categorization for the adaptive repair controller.

Categories are GENERAL (they describe the shape of a failure, never the
task): grounded in the Session-035 archive mining (see
experiments/z036/prior-mining.json) and the Session-036 brief:

  syntax             parse failure / truncation / brace imbalance
  missing_export     required export or handler absent (anchor-only files)
  missing_literal    the "one-literal gap": a single literal/expression/
                     UI string never appears in executable positions
  missing_call       required API/db call chain absent
  wrong_contract     right shape, wrong semantics (forbidden patterns,
                     wrong filters, wrong query construction)
  demo_contamination demo-domain identifiers leaking into the target
  type_error         tsc/type-level mismatches (TS2xxx)
  ui_state           dynamic failure: component renders but state
                     integration broken (only detectable by tests)
  interface_mismatch cross-file contract violated (db.<model> absent,
                     import missing)
"""
from __future__ import annotations

import re

CATEGORIES = [
    "syntax", "missing_export", "missing_literal", "missing_call",
    "wrong_contract", "demo_contamination", "type_error", "ui_state",
    "interface_mismatch",
]

_TS_TYPE = re.compile(r"error TS\d+")


def categorize(gate_failures: list[str], tsc_errors: list[str] | None = None,
               dynamic_failures: list[str] | None = None) -> str:
    """Map raw failure signals to ONE general category (primary defect).

    Priority: syntax > type > export > interface > contamination >
    call > literal > contract > ui_state.  A file must parse before any
    semantic category is meaningful, so syntax wins; among semantic
    failures the most specific mechanical signal wins.
    """
    gf = gate_failures or []
    te = tsc_errors or []
    df = dynamic_failures or []

    def any_fail(pred):
        return any(pred(f) for f in gf + te + df)

    if any_fail(lambda f: f.startswith("parse:")):
        return "syntax"
    if any_fail(lambda f: "unbalanced" in f or "truncated" in f):
        return "syntax"
    if te and any(_TS_TYPE.search(t) for t in te):
        return "type_error"
    if any_fail(lambda f: f.startswith("exports:")):
        return "missing_export"
    if any_fail(lambda f: f.startswith("interfaces:")):
        return "interface_mismatch"
    if any_fail(lambda f: "demo echo" in f.lower() or "contamination" in f.lower()):
        return "demo_contamination"
    if any_fail(lambda f: f.startswith("calls:") or f.startswith("accesses:")
                or "db." in f):
        return "missing_call"
    if any_fail(lambda f: f.startswith("uiStrings:") or "missing" in f.lower()):
        return "missing_literal"
    if any_fail(lambda f: f.startswith("forbidden") or "forbidden" in f):
        return "wrong_contract"
    if any_fail(lambda f: f.startswith("echo:")):
        return "demo_contamination"
    if df:
        return "ui_state"
    if any_fail(lambda f: f.startswith("reachability:")):
        return "wrong_contract"
    if any_fail(lambda f: f.startswith("incomplete:")):
        return "syntax"
    return "wrong_contract"
