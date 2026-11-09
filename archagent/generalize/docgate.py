"""SESSION 037 — PHASE 8: controlled documentation-retrieval workflow.

Design (from the task book):
  1. classify the knowledge gap from the failure signature
  2. resolve the pinned documentation snippet for the INSTALLED version
  3. inject a short, clearly-labeled DOC-FACT block (documentation facts
     are kept visually distinct from inferred choices)
  4. DEFAULT OFF: the block is only enabled system-wide if a controlled
     A/B run proves improvement (see validate_docgate.py)

Session-036 context: the `doc_lookup` strategy went 0/8 — retrieval was
never demonstrated to help.  This module makes the workflow measurable
instead of assumed.

The corpus is pinned offline (embedded constants with source + version)
because runtime web retrieval is not feasible on 2 CPU threads and would
make runs unreproducible.  Every snippet records where it came from; a
snippet is a DOC-FACT only if it restates documentation, and a CHOICE if
it encodes a decision we made.
"""
from __future__ import annotations

# ------------------------------------------------------------- corpus

CORPUS_VERSION = "docgate-v1-2026-11-09"

DOCS: dict[str, dict] = {
    "prisma-relation-optional": {
        "gap": "relation",
        "source": "Prisma docs, Relations reference (prisma 6.x, pinned)",
        "kind": "DOC-FACT",
        "lines": [
            "An optional relation needs `?` on the field, `?` on its",
            "backing scalar, and the relation attribute:",
            "  user     User?   @relation(fields: [userId], references: [id])",
            "  userId   String?",
        ],
    },
    "prisma-relation-list": {
        "gap": "relation",
        "source": "Prisma docs, Relations reference (prisma 6.x, pinned)",
        "kind": "DOC-FACT",
        "lines": [
            "The 'many' side of a relation is a list field with no backing",
            "scalar; the 'one' side carries the attribute:",
            "  posts    Post[]",
            "  author   User    @relation(fields: [authorId], references: [id])",
            "  authorId String",
        ],
    },
    "prisma-self-relation": {
        "gap": "relation",
        "source": "Prisma docs, Self-relations (prisma 6.x, pinned)",
        "kind": "DOC-FACT",
        "lines": [
            "A self-relation names itself in the relation attribute:",
            "  parent   Folder?   @relation(\"children\", fields: [parentId], references: [id])",
            "  parentId String?",
            "  children Folder[]  @relation(\"children\")",
        ],
    },
    "next-route-post": {
        "gap": "route-shape",
        "source": "Next.js App Router docs, Route Handlers (next 15/16, pinned)",
        "kind": "DOC-FACT",
        "lines": [
            "A route handler exports an async function named after the HTTP",
            "method and returns NextResponse.json:",
            "  export async function POST(request: Request) {",
            "    const body = await request.json();",
            "    return NextResponse.json({ ... }, { status: 201 });",
            "  }",
        ],
    },
    "next-route-get": {
        "gap": "route-shape",
        "source": "Next.js App Router docs, Route Handlers (next 15/16, pinned)",
        "kind": "DOC-FACT",
        "lines": [
            "GET handlers may read search params from the request URL:",
            "  export async function GET(request: Request) {",
            "    const { searchParams } = new URL(request.url);",
            "    const q = searchParams.get(\"q\");",
            "    return NextResponse.json(items);",
            "  }",
        ],
    },
    "ts-boundary": {
        "gap": "invariant",
        "source": "CHOICE (not documentation): our house pattern",
        "kind": "CHOICE",
        "lines": [
            "For range checks, write the boundaries as explicit comparisons",
            "and test the exact boundary values separately:",
            "  return min <= v && v <= max;   // closed interval",
            "(docs cannot tell you which interval YOUR spec means — the",
            " spec's case table is the source of truth)",
        ],
    },
}


# --------------------------------------------------- gap classification

def classify_gap(piece_kind: str, failures: list[str]) -> str | None:
    """Map a failure signature to a knowledge gap.

    Returns one of 'relation' | 'route-shape' | 'invariant' | None.
    Conservative: unknown signatures map to None (no doc injection).
    """
    if not failures:
        return None
    blob = " ".join(failures).lower()
    if piece_kind == "prisma-model":
        if any(k in blob for k in ("relation", "backing", "scalar",
                                   "fields:", "references:")):
            return "relation"
        return None
    if piece_kind == "route-handler":
        if any(k in blob for k in ("call", "handler", "nextresponse",
                                   "request", "await", "method")):
            return "route-shape"
        return None
    if piece_kind == "invariant":
        if any(k in blob for k in ("case", "boundary", "value",
                                   "returned", "expected")):
            return "invariant"
        return None
    return None


def pick_doc(piece_kind: str, spec: str, failures: list[str]) -> dict | None:
    """Choose the pinned snippet for the gap, if any."""
    gap = classify_gap(piece_kind, failures)
    if gap is None:
        return None
    spec_l = (spec or "").lower()
    if gap == "relation":
        if "self" in spec_l or "parent" in spec_l or "folder" in spec_l:
            return DOCS["prisma-self-relation"]
        if "optional" in spec_l or "?" in spec_l:
            return DOCS["prisma-relation-optional"]
        return DOCS["prisma-relation-list"]
    if gap == "route-shape":
        return DOCS["next-route-post" if "post" in spec_l
                    else "next-route-get"]
    if gap == "invariant":
        return DOCS["ts-boundary"]
    return None


def doc_block(doc: dict | None) -> str:
    """Render the documentation block for prompt injection.

    Documentation facts and house choices are labeled differently —
    the model must be able to tell them apart.
    """
    if doc is None:
        return ""
    head = (f"[{doc['kind']}] pinned documentation ({CORPUS_VERSION}) — "
            f"source: {doc['source']}")
    body = "\n".join(doc["lines"])
    return f"{head}\n{body}\n"
