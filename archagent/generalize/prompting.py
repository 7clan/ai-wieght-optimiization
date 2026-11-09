"""SESSION 037 — PHASE 2: prompt construction enforcing Phase-1 lessons.

Laws implemented here (each traces to a root cause in Phase 1):

  L-ANCHOR  the anchor sits INSIDE the target construct (open paren or
            open brace) — never a bare import line (H5 early-EOS: 46/147
            Session-036 candidates died echoing a file-start anchor).
  L-DEMO    demo-completeness: the demo contains every construct shape
            the piece requires, in a DIFFERENT domain (P2: relation-free
            schema demo => 0/16 relations; 3-member demo interface =>
            `floor` dropped 8x).
  L-BOUND   specs carry <= 6 clauses (P1: 24-clause one-shot contracts
            exceeded integration capacity while the overlap piece alone
            was producible).
  L-DIFF    an explicit "change the demo's domain to yours" instruction
            (P4: demo-verbatim copying).
  L-EOS     near-empty candidates are detected, never scored as strategy
            failures; a forced-continuation retry follows.
  L-TRIM    prose tails after the construct are cut mechanically
            (M4); brace-balance is CHECKED, never auto-fixed.
"""
from __future__ import annotations

import re

NEAR_EMPTY_CHARS = 100

# ----------------------------------------------------------- demo checks

_DEMO_REQUIREMENTS = {
    "prisma-model": [
        (r"@\w+\(", "a field attribute"),
        (r"@\w+\([^)]*fields:\s*\[[^\]]+\][^)]*references:\s*\[", None),
    ],
    "invariant": [
        (r"return\s+", "a return statement"),
        (r"(?:<|>|<=|>=|&&|\|\|)", "a comparison/boolean operator"),
    ],
    "route-handler": [
        (r"NextResponse\.json", "NextResponse.json call"),
    ],
    "hook": [(r"await\s+fetch", "an awaited fetch")],
    "component": [(r"<[a-zA-Z]", "JSX")],
    "page": [(r"<[a-zA-Z]", "JSX")],
}


def validate_demo(piece) -> list[str]:
    """Check demo-completeness (L-DEMO).  Returns violation strings."""
    errs = []
    demo = (piece.demo or "").strip()
    if not demo:
        return [f"{piece.pid}: no demo (L-DEMO requires one)"]
    reqs = _DEMO_REQUIREMENTS.get(piece.kind, [])
    for pat, what in reqs:
        if what is None:      # conditional: relation requirement
            has_relation = any(
                r.kind == "many-to-one"
                for e in (piece.ir.entities if piece.ir else [])
                if e.pid == piece.pid for r in e.relations)
            if has_relation and not re.search(pat, demo):
                errs.append(f"{piece.pid}: demo lacks an @relation(fields:"
                            f"/references:) example while the piece requires "
                            f"one (P2 lesson)")
        elif not re.search(pat, demo):
            errs.append(f"{piece.pid}: demo lacks {what}")
    return errs


# -------------------------------------------------------- prompt builder

def checklist_for(piece) -> str:
    """L-CHECKLIST (measured in curriculum A bring-up): render the
    piece's required elements as a comment line INSIDE the construct,
    right after the anchor's opening line.  Information content is
    IDENTICAL to the spec (no teacher solution added) — only the
    PLACEMENT changes: the model reads the checklist exactly where it
    writes, which defeats demo-field copying (6/6 clean vs 0/6 with
    spec-only placement in the A/B seed test)."""
    k = piece.kind
    if k == "prisma-model":
        items = []
        for m in piece.gate.get("models", []):
            for f in m.get("fields", []):
                desc = f["name"]
                if f.get("type"):
                    desc += f" {f['type']}"
                if f.get("isList"):
                    desc += "[]"
                if f.get("optional"):
                    desc += "?"
                attrs = f.get("attrsIncludes") or []
                if attrs:
                    desc += " (" + ", ".join(attrs) + ")"
                items.append(desc)
        if not items:
            return ""
        return ("  // required fields: " + "; ".join(items)
                + "\n")
    if k == "route-handler":
        calls = piece.gate.get("calls", [])
        if not calls:
            return ""
        return ("  // required calls: " + ", ".join(calls) + "\n")
    if k == "invariant":
        return ""
    return ""


def build_piece_prompt(piece, *, retry: int = 0,
                       extra_feedback: str = "",
                       opening: str = "") -> str:
    """Whole-construct prompt for one piece.

    retry=0  canonical form.  retry>=1 adds the failing-check feedback
    (counterexample or gate failure) and a STRONGER continue directive.
    opening: optional replacement for the domain-diff line (prompt
    mutation for resample diversity — the Phase-5 variant set).
    """
    concept = piece.ir.concept if piece.ir else ""
    parts = [concept, "", piece.demo, ""]
    parts.append(f"Now YOUR task: {piece.spec}")
    parts.append(opening or ("Adapt the example's PATTERNS to this "
                             "task's names — never copy its domain "
                             "words."))
    if extra_feedback:
        parts.append("")
        parts.append("Your previous attempt had these verified problems:")
        parts.append(extra_feedback)
        parts.append("Fix exactly those; keep everything else.")
    if retry == 0:
        parts.append("")
        parts.append(f"Write the complete {piece.kind} now.  The first "
                     "line is already written; continue from it:")
    else:
        parts.append("")
        parts.append("Write the corrected complete construct now.  The "
                     "first line is already written; continue from it:")
    parts.append(piece.anchor + checklist_for(piece))
    return "\n".join(parts)


def forced_continuation_prompt(piece) -> str:
    """L-EOS retry: the anchor extended so the model is already inside
    the construct body; stopping is no longer 'a complete file'."""
    if piece.kind == "route-handler":
        method = piece.gate["handlers"][0]
        anchor = f"export async function {method}(req: NextRequest) {{\n"
    elif piece.kind == "invariant" and piece.oracle:
        sig = piece.oracle["signature"]
        params = sig[sig.index("(") + 1:].rstrip(")").strip()
        anchor = f"{sig.split('(')[0]}({params}) {{\n"
    elif piece.kind == "component":
        anchor = f"export function {getattr(piece, 'name', '')}( {{\n" if hasattr(piece, 'name') else piece.anchor
    else:
        anchor = piece.anchor + (" {\n" if not piece.anchor.endswith("{") else "\n")
    return _with_anchor(piece, anchor)


def _with_anchor(piece, anchor: str, retry: int = 1) -> str:
    concept = piece.ir.concept if piece.ir else ""
    parts = [concept, "", piece.demo, ""]
    parts.append(f"Now YOUR task: {piece.spec}")
    parts.append("Adapt the example's PATTERNS to this task's names — "
                 "never copy its domain words.")
    parts.append("")
    parts.append("Your last attempt stopped before writing anything.  "
                 "Continue writing the construct body now, starting with "
                 "its first statement:")
    parts.append(anchor)
    return "\n".join(parts)


# ------------------------------------------------------- extraction/trim

_PROSE_TAIL = re.compile(
    r"\n\s*(?:\d+\.|-|Note|Notes|Here|This |In |If |The above|Now |"
    r"Explanation|As |Let |We |You )", re.I)

# Prompt-mutation variants for resample diversity (Phase-5 seed set;
# used when dedup shows the sampler is stuck in one attractor).
RESAMPLE_OPENINGS = [
    "Rewrite the example for this task: same structure, different "
    "domain, every required element present.",
    "Write this task's version from scratch. List every required "
    "field first, then write the construct with exactly those fields.",
    "Use the example only as a shape reference. All names, fields and "
    "relations come from THIS task's requirements above.",
]


def extract_construct(text: str, kind: str) -> str:
    """Trim prose tails and stop at the natural construct end (L-TRIM).

    Mechanical post-processing ONLY: nothing is added; trailing non-code
    and anything after the construct closes is removed.
    """
    t = text.strip()
    m = _PROSE_TAIL.search(t)
    if m and m.start() > 80:
        t = t[:m.start()]
    # cut at a fenced ``` tail if the model started one
    if "```" in t:
        t = t.split("```")[0]
    # stop when brace depth returns to zero after the construct opened
    depth = 0
    opened = False
    for i, ch in enumerate(t):
        if ch == "{":
            depth += 1
            opened = True
        elif ch == "}":
            depth -= 1
            if opened and depth <= 0:
                t = t[: i + 1]
                break
    if kind == "prisma-model":
        # stop after the model block closes
        m = re.search(r"^model\s+\w+\s*\{[^}]*\}", t, re.M | re.S)
        if m:
            t = m.group(0)
        # MECHANICAL NORMALIZATION (discovered via the prisma-validate
        # behavioral probe): the prisma grammar does not accept a field
        # on the same line as the opening brace — `model Band {  id
        # String` parses as a model WITHOUT the id field.  Anchor-based
        # assembly (anchor + continuation) produces exactly that shape.
        t = re.sub(r"^(\s*model\s+\w+\s*\{)[ \t]+(\S)", r"\1\n  \2", t)
    return t.rstrip()


def is_near_empty(candidate: str) -> bool:
    return len(candidate.strip()) < NEAR_EMPTY_CHARS


def braces_balanced(text: str) -> bool:
    depth = 0
    in_str = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


# ------------------------------------------------------- repair prompts

def _spec_clauses_for(failures: list[str], spec: str) -> list[str]:
    """Map gate failures back to the spec sentences that declare the
    missing element (spec material the model already saw — never a
    teacher-written solution)."""
    sentences = [s.strip() for s in
                 re.split(r"(?<=[.;])\s+", spec) if s.strip()]
    out = []
    for f in failures[:4]:
        m = (re.search(r"schema: \w+\.(\w+) missing", f)
             or re.search(r"schema: \w+\.(\w+) not declared", f)
             or re.search(r"types: \w+\.(\w+) missing", f)
             or re.search(r"exports: HTTP handler '(\w+)'", f)
             or re.search(r"calls: '([\w.]+)'", f)
             or re.search(r"accesses: '([\w.]+)'", f)
             or re.search(r"uiStrings: '([^']+)'", f)
             or re.search(r"invariant: function '(\w+)'", f))
        if not m:
            continue
        token = m.group(1)
        hits = [s for s in sentences if token in s]
        if hits:
            out.append(hits[0])
        else:
            out.append(f"add the missing element: {token}")
    return out


def build_repair_prompt(piece, failing_clauses: list[str],
                        counterexample: str = "",
                        code: str = "") -> tuple[str, str, str]:
    """Micro-repair prompt (FIM-shaped).  Returns (prefix, suffix,
    instruction).

    The instruction quotes the piece's OWN spec clauses that declare
    the missing element plus the observed counterexample — the model
    saw all of this at generation time; nothing teacher-written is
    added (provenance discipline preserved).
    """
    spec = getattr(piece, "spec", "")
    instr_parts = ["this attempt must additionally satisfy:"]
    for c in _spec_clauses_for(failing_clauses, spec)[:3]:
        instr_parts.append(f"- {c}")
    if not instr_parts[1:]:
        for c in failing_clauses[:3]:
            instr_parts.append(f"- {c}")
    if counterexample:
        instr_parts.append(f"verified failure: {counterexample}")
    instr_parts.append("write the missing logic; do not remove existing "
                       "logic")
    instruction = " ".join(instr_parts)[:400]

    # insertion point: for a missing CALL/branch, the gap sits right
    # before the final happy-path (create/findMany) — use the last
    # top-level `const`/`return` line of the construct as the seam.
    if not code:
        return "", "", instruction
    lines = code.split("\n")
    kind = getattr(piece, "kind", "")
    if kind == "prisma-model":
        # insert INSIDE the model block: before the closing brace
        close = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "}":
                close = i
                break
        seam = close if close is not None else len(lines)
        prefix = "\n".join(lines[:seam])
        suffix = "\n".join(lines[seam:])
        return prefix, suffix, instruction
    seam = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"\s*(const |let |return |await db\.)", lines[i]):
            seam = i
            break
    prefix = "\n".join(lines[:seam])
    suffix = "\n".join(lines[seam:seam + 6])
    return prefix, suffix, instruction
