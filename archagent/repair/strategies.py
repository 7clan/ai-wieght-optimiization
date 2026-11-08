"""SESSION 036 — PHASE 2/3 (TRUSTED-SCAFFOLD).

Repair strategies.  Each strategy turns a *defect* (file + failing
contract + failure signals) into one candidate patch via the frozen
model.  Strategies are GENERAL: they manipulate code structure, never
task-specific content.

Every attempt records its prompt and provenance level:
  L1 QWEN-CHOSEN      the model wrote the correction from a diagnosis
                      alone (no teacher-named fix)         [this module]
  L2 QWEN-APPLIED     a teacher named the exact token diff and the model
                      executed it                          [apply_named]
  L3 HARNESS-INSERTED deterministic insertion of a known fix
                                                      [not here — harness]
  L4 TEACHER-WRITTEN  teacher wrote the code              [never here]
"""
from __future__ import annotations

import re

# ------------------------------------------------------------------ utils

def locate_region(code: str, token: str, hint: dict | None = None) -> tuple[str, str]:
    """Return (prefix, suffix) around the most plausible defective region.

    `hint` may carry contract-provided region context; otherwise we
    auto-locate by identifier proximity: the last usage site of the
    token's root identifier, extended to line boundaries.
    """
    if hint and "prefix" in hint:
        return hint["prefix"], hint.get("suffix", "")
    root = re.split(r"[.:()\[\]\s]", token)[0] or token
    lines = code.split("\n")
    best = None
    for i, ln in enumerate(lines):
        if re.search(rf"\b{re.escape(root)}\b", ln):
            best = i
    if best is None:
        # fall back to the end of the file's first top-level block
        best = min(len(lines) - 1, 20)
    # region = the located line plus one line of following context
    start = "\n".join(lines[:best + 1])
    end = "\n".join(lines[best + 1:best + 3])
    return start, end


def _anchor_of(defect: dict) -> str:
    """Anchor line: from the contract, else the current file's first
    non-empty line (existing-file repair), else the import line."""
    c = defect.get("contract") or {}
    if c.get("anchor"):
        return c["anchor"]
    code = defect.get("code") or ""
    for ln in code.split("\n"):
        if ln.strip():
            return ln
    return "import { NextResponse } from 'next/server'"


def _fdiag(gate_failures: list[str], limit: int = 700) -> str:
    return "\n".join(gate_failures[:6])[:limit]


# ------------------------------------------------------------- strategies

def s_regen_whole(model, defect: dict, seed: int):
    """Direct source regeneration with failure feedback (fresh seed)."""
    c = defect["contract"]
    parts = [defect.get("concept", ""), "", c.get("demo", ""), ""]
    parts.append(f"Now YOUR task.  Write the file {c['file']} for the "
                 "application.")
    parts.append(c.get("spec") or c.get("instruction") or "")
    if diag := defect.get("diagnosis"):
        parts.append("\nRequirement not yet met:")
        parts.append(diag)
        parts.append("Satisfy it.")
    elif gate_failures := defect.get("gate_failures"):
        parts.append("\nThe automated checks reported:")
        parts.append(_fdiag(gate_failures))
        parts.append("Fix exactly that.")
    parts.append("\nWrite the complete file now.  The first line is "
                 "already written; continue from it:")
    parts.append(_anchor_of(defect))
    prompt = "\n".join(parts)
    out, usage = model.generate(prompt, max_tokens=c.get("max_tokens", 700),
                                seed=seed, stochastic=True)
    code = _anchor_of(defect) + "\n" + out
    return code, usage, prompt, "L1"


def s_exact_shape(model, defect: dict, seed: int):
    """Exact-shape whole-file contract (Session-034 format), no feedback."""
    c = defect["contract"]
    parts = [defect.get("concept", ""), "", c.get("demo", ""), ""]
    parts.append(f"Now YOUR task.  Write the file {c['file']} for the "
                 "application.")
    parts.append(c.get("spec") or c.get("instruction") or "")
    parts.append("\nWrite the complete file now.  The first line is "
                 "already written; continue from it:")
    parts.append(_anchor_of(defect))
    prompt = "\n".join(parts)
    out, usage = model.generate(prompt, max_tokens=c.get("max_tokens", 700),
                                seed=seed, stochastic=True)
    code = _anchor_of(defect) + "\n" + out
    return code, usage, prompt, "L1"


def s_body_completion(model, defect: dict, seed: int):
    """Function-body completion with anchors around the target body."""
    c = defect["contract"]
    region = defect.get("region") or {}
    prefix = region.get("prefix") or _anchor_of(defect)
    suffix = region.get("suffix") or ""
    parts = []
    if demo := c.get("body_demo"):
        parts.append(demo)
        parts.append("")
    parts.append(f"Write the body for the handler in {c['file']}.")
    parts.append(c.get("body_spec") or c.get("spec") or c.get("instruction") or "")
    if diag := defect.get("diagnosis"):
        parts.append("\nRequirement not yet met:")
        parts.append(diag)
    elif gf := defect.get("gate_failures"):
        parts.append("\nThe automated checks reported:")
        parts.append(_fdiag(gf))
    parts.append("\nThe code before the gap:")
    parts.append(prefix[-900:])
    parts.append("\nThe code after the gap:")
    parts.append(suffix[:400])
    prompt = "\n".join(parts)
    out, usage = model.generate(prompt, max_tokens=c.get("body_max_tokens", 420),
                                seed=seed, stochastic=True)
    body = _trim_body(out)
    code = prefix + "\n" + body + "\n" + suffix
    return code, usage, prompt, "L1"


def _trim_body(text: str) -> str:
    """Cut prose tails and keep a balanced-looking body prefix."""
    text = text.strip()
    # stop at a numbered/bulleted prose tail (documented Qwen behavior)
    m = re.search(r"\n\s*(?:\d+\.|-)\s+(?:The|This|Note|Here|In |If )",
                  text)
    if m and m.start() > 60:
        text = text[:m.start()]
    return text


def s_fim_micro(model, defect: dict, seed: int):
    """FIM micro-patch: tiny instruction adjacent to a tiny gap.

    The instruction is derived from the DIAGNOSIS (which check failed),
    never from a teacher-named fix — the model must choose the code.
    """
    c = defect["contract"]
    token = _token_from_failures(defect.get("gate_failures", []))
    prefix, suffix = locate_region(defect["code"], token,
                                   defect.get("region"))
    instr = _micro_instruction(defect)
    out, usage = model.fim(prefix, suffix, instructions=instr,
                           max_tokens=64, seed=seed, stochastic=True)
    code = prefix + out + suffix
    return code, usage, f"[FIM] {instr}", "L1"


def _token_from_failures(failures: list[str]) -> str:
    for f in failures:
        m = re.search(r"missing '([^']+)'", f)
        if m:
            return m.group(1)
        m = re.search(r"'([^']+)' not found", f)
        if m:
            return m.group(1)
    return ""


def _micro_instruction(defect: dict) -> str:
    """<=15-word, code-shaped instruction.

    Provenance-critical: if `diagnosis` (semantic, teacher-written
    requirement WITHOUT code) is present the model must CHOOSE the fix
    (L1).  Otherwise we fall back to the mechanical gate failure, which
    may quote the expected code — that is L2 (applying a named fix).
    """
    if diag := defect.get("diagnosis"):
        return diag[:110]
    cat = defect.get("category", "")
    tok = _token_from_failures(defect.get("gate_failures", []))
    if cat == "missing_literal" and tok:
        return f"add the {tok} check here"
    if cat == "missing_call" and tok:
        return f"call {tok} here"
    if cat == "syntax":
        return "fix the syntax here"
    if cat == "missing_export":
        return "export the handler here"
    if tok:
        return f"use {tok} here"
    return "fix this region"


def s_ast_replace(model, defect: dict, seed: int):
    """AST-constrained replacement: FIM over ONE node-sized region.

    The region is the smallest block containing the failing token's
    usage, or the whole handler if no token is known.
    """
    token = _token_from_failures(defect.get("gate_failures", []))
    code = defect["code"]
    prefix, suffix = locate_region(code, token or "", defect.get("region"))
    # widen prefix to the start of its last statement
    lines = prefix.split("\n")
    while lines and (not lines[-1].strip()
                     or lines[-1].lstrip().startswith(("//", "*", "/*"))):
        lines.pop()
    prefix = "\n".join(lines)
    instr = (f"rewrite this one statement: {defect['diagnosis']}"
             if defect.get("diagnosis") else
             "rewrite this one statement to satisfy: "
             + _fdiag(defect.get("gate_failures", []), 200))
    out, usage = model.fim(prefix, suffix, instructions=instr,
                           max_tokens=96, seed=seed, stochastic=True)
    return prefix + out + suffix, usage, f"[AST-REPLACE] {instr}", "L1"


def s_compiler_guided(model, defect: dict, seed: int):
    """Feed tsc diagnostics into a FIM around the error location."""
    errs = defect.get("tsc_errors") or []
    if not errs:
        # degrade to micro with gate failures as the "diagnostics"
        return s_fim_micro(model, defect, seed)
    first = errs[0]
    m = re.search(r"\((\d+),(\d+)\)", first)
    code = defect["code"]
    lines = code.split("\n")
    if m:
        ln = int(m.group(1)) - 1
        ln = max(0, min(ln, len(lines) - 1))
    else:
        ln = len(lines) // 2
    prefix = "\n".join(lines[:ln + 1])
    suffix = "\n".join(lines[ln + 1:ln + 4])
    instr = ("compiler error here: "
             + first.split("\n")[0][:140] + " — fix it")
    out, usage = model.fim(prefix, suffix, instructions=instr,
                           max_tokens=96, seed=seed, stochastic=True)
    return prefix + out + suffix, usage, f"[COMPILER] {instr}", "L1"


def s_doc_lookup(model, defect: dict, seed: int, docs: str = ""):
    """Documentation-assisted completion (Phase 4 supplies `docs`)."""
    c = defect["contract"]
    excerpt = (docs or "").strip()[:1200]
    parts = []
    if excerpt:
        parts.append("Reference documentation (use the API correctly):")
        parts.append(excerpt)
        parts.append("")
    region = defect.get("region") or {}
    prefix = region.get("prefix") or _anchor_of(defect)
    suffix = region.get("suffix") or ""
    parts.append(f"Using that documentation, write the body for "
                 f"{c['file']}:")
    parts.append(c.get("body_spec") or c.get("spec") or c.get("instruction") or "")
    if gf := defect.get("gate_failures"):
        parts.append("\nChecks reported:")
        parts.append(_fdiag(gf))
    parts.append("\nCode before the gap:")
    parts.append(prefix[-700:])
    prompt = "\n".join(parts)
    out, usage = model.generate(prompt, max_tokens=c.get("body_max_tokens", 420),
                                seed=seed, stochastic=True)
    body = _trim_body(out)
    return prefix + "\n" + body + "\n" + suffix, usage, prompt, "L1"


def s_contract_split(model, defect: dict, seed: int):
    """Decompose: generate ONE single-expectation piece and insert it.

    The controller calls this per missing expectation; here we generate
    the smallest piece the contract asks for (first missing item).
    """
    c = defect["contract"]
    failures = defect.get("gate_failures", [])
    item = _token_from_failures(failures) or "the required element"
    region = defect.get("region") or {}
    prefix = region.get("prefix") or _anchor_of(defect)
    suffix = region.get("suffix") or ""
    parts = [
        f"Write only the single piece described below for {c['file']}.",
        f"Piece: {item}.",
        "Write nothing else — just that piece.",
        "\nContext (code before):",
        prefix[-600:],
    ]
    prompt = "\n".join(parts)
    out, usage = model.generate(prompt, max_tokens=120, seed=seed,
                                stochastic=True)
    piece = _trim_body(out)
    return prefix + "\n" + piece + "\n" + suffix, usage, prompt, "L1"


def s_minimal_diff(model, defect: dict, seed: int):
    """Minimal-diff: mark the defective line(s), rewrite only those."""
    token = _token_from_failures(defect.get("gate_failures", []))
    code = defect["code"]
    prefix, suffix = locate_region(code, token, defect.get("region"))
    last_line = prefix.split("\n")[-1]
    instr = ("rewrite only this line: " + defect["diagnosis"]
             if defect.get("diagnosis") else
             "rewrite only this line correctly: " + _fdiag(
               defect.get("gate_failures", []), 160))
    out, usage = model.fim(prefix, suffix, instructions=instr,
                           max_tokens=48, seed=seed, stochastic=True)
    _ = last_line
    return prefix + out + suffix, usage, f"[MIN-DIFF] {instr}", "L1"


def s_apply_named(model, defect: dict, seed: int, named_fix: str):
    """L2 QWEN-APPLIED: the teacher NAMES the exact token diff; the model
    must still execute it.  NEVER counted as independent capability —
    a separate metric from every L1 strategy above."""
    region = defect.get("region") or {}
    prefix = region.get("prefix") or _anchor_of(defect)
    suffix = region.get("suffix") or ""
    instr = f"change this to: {named_fix}"
    out, usage = model.fim(prefix, suffix, instructions=instr,
                           max_tokens=48, seed=seed, stochastic=True)
    return prefix + out + suffix, usage, f"[APPLY-NAMED] {instr}", "L2"


STRATEGY_FNS = {
    "regen_whole": s_regen_whole,
    "exact_shape": s_exact_shape,
    "body_completion": s_body_completion,
    "fim_micro": s_fim_micro,
    "ast_replace": s_ast_replace,
    "compiler_guided": s_compiler_guided,
    "doc_lookup": s_doc_lookup,
    "contract_split": s_contract_split,
    "minimal_diff": s_minimal_diff,
}


def run_strategy(model, name: str, defect: dict, seed: int,
                  docs: str = "", named_fix: str = ""):
    if name == "apply_named":
        return s_apply_named(model, defect, seed, named_fix)
    if name == "doc_lookup":
        return s_doc_lookup(model, defect, seed, docs=docs)
    return STRATEGY_FNS[name](model, defect, seed)
