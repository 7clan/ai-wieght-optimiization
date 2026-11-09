"""SESSION 037 — PHASE 8 validation: does the doc block help?

Controlled A/B on 4 FRESH mini-tasks (none from the frozen suite, none
from the curricula — no contamination of Phase 10):

  DG-1  prisma one-to-many, required FK        (2 models)
  DG-2  prisma optional FK                     (2 models)
  DG-3  route POST w/ validation + create
  DG-4  route GET w/ search filter

Both arms use the SAME Track-B-style prompt (demo + spec + anchor),
same seeds, same budget (3 attempts / 900 tokens per piece).  The ONLY
difference: the with-doc arm injects the pinned documentation block
selected by docgate.pick_doc from the FIRST attempt's failures (and
re-selected on later attempts).

Decision rule (recorded, machine-checkable): the doc block becomes
engine-default ONLY if with-doc resolves strictly more pieces at <=
the tokens of without-doc.  Otherwise it stays an opt-in tool.

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.validate_docgate
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.run_curricula import (  # noqa: E402
    _GateRunner, baseline_prompt, _SCAFFOLD_HEAD)
from archagent.generalize import prompting, docgate  # noqa: E402

WS = Path("/home/z/my-project")
OUT = ROOT / "experiments" / "z037-generalization" / "docgate"
BUDGET_TOKENS = 900
BUDGET_ATTEMPTS = 3

DEMO_PRISMA = ("model Singer {\n  id     String  @id @default(cuid())\n"
               "  name   String\n  albums Album[]\n}\n\n"
               "model Album {\n  id       String  @id @default(cuid())\n"
               "  title    String\n  singerId String\n"
               "  singer   Singer  @relation(fields: [singerId], "
               "references: [id])\n}")

DEMO_ROUTE = ("// a bakery order-taking route (different domain)\n"
              "import { NextRequest, NextResponse } from 'next/server'\n"
              "import { db } from '@/lib/db'\n\n"
              "export async function POST(request: NextRequest) {\n"
              "  const body = await request.json()\n"
              "  const name = String(body.name ?? '').trim()\n"
              "  if (!name) {\n"
              "    return NextResponse.json(\n"
              "      { error: 'Name is required' }, { status: 400 })\n"
              "  }\n"
              "  const customer = await db.customer.findUnique({\n"
              "    where: { id: body.customerId } })\n"
              "  if (!customer) {\n"
              "    return NextResponse.json(\n"
              "      { error: 'Customer not found' }, { status: 404 })\n"
              "  }\n"
              "  const order = await db.order.create({\n"
              "    data: { name, customerId: body.customerId } })\n"
              "  return NextResponse.json({ order }, { status: 201 })\n"
              "}\n")

TASKS = [
    {   # DG-1 one-to-many required FK, new domain (harbor)
        "pid": "dg-harbor",
        "app": "harbor",
        "entities": [
            {"pid": "dg-dock", "name": "Dock", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "name", "type": "String"}],
             "relations": [
                {"name": "berths", "target": "Berth", "kind": "one-to-many",
                 "is_list": True}]},
            {"pid": "dg-berth", "name": "Berth", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "code", "type": "String"},
                {"name": "dockId", "type": "String"}],
             "relations": [
                {"name": "dock", "target": "Dock", "kind": "many-to-one",
                 "is_list": False, "fk_field": "dockId"}]},
        ],
        "routes": [], "ui": [],
    },
    {   # DG-2 optional FK, new domain (atelier)
        "pid": "dg-atelier",
        "app": "atelier",
        "entities": [
            {"pid": "dg-artist", "name": "Artist", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "handle", "type": "String"}],
             "relations": [
                {"name": "artworks", "target": "Artwork", "kind": "one-to-many",
                 "is_list": True}]},
            {"pid": "dg-artwork", "name": "Artwork", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "title", "type": "String"},
                {"name": "artistId", "type": "String", "optional": True}],
             "relations": [
                {"name": "artist", "target": "Artist", "kind": "many-to-one",
                 "is_list": False, "fk_field": "artistId", "optional": True}]},
        ],
        "routes": [], "ui": [],
    },
    {   # DG-3 route POST validation + create (clinics)
        "pid": "dg-clinic",
        "app": "clinics",
        "entities": [
            {"pid": "dg-patient", "name": "Patient", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "name", "type": "String"}], "relations": []},
        ],
        "routes": [
            {"pid": "dg-clinic-post", "method": "POST",
             "path": "/api/visits", "file": "src/app/api/visits/route.ts",
             "clauses": [
                 "Export POST. Await request.json.",
                 "Trim reason with String; when empty return 400 'Reason is required'.",
                 "Call db.patient.findUnique where id body.patientId; when missing return 404 'Patient not found'.",
                 "Call db.visit.create with data reason, patientId.",
                 "Return NextResponse.json with visit and status 201."],
             "responses": [
                 {"status": 400, "message": "Reason is required", "shape": {}},
                 {"status": 404, "message": "Patient not found", "shape": {}},
                 {"status": 201, "shape": {"visit": "Visit"}}],
             "calls": ["db.patient.findUnique", "db.visit.create",
                       "NextResponse.json"],
             "uses_invariants": [], "demo_domain": DEMO_ROUTE,
             "probe_seed": 7, "probe_cases": []},
        ],
        "ui": [],
    },
    {   # DG-4 route GET with search filter (depots)
        "pid": "dg-depot",
        "app": "depots",
        "entities": [
            {"pid": "dg-tool", "name": "Tool", "fields": [
                {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
                {"name": "label", "type": "String"}], "relations": []},
        ],
        "routes": [
            {"pid": "dg-depot-get", "method": "GET",
             "path": "/api/tools", "file": "src/app/api/tools/route.ts",
             "clauses": [
                 "Export GET. Read searchParams from new URL(request.url).",
                 "Read q from searchParams get 'q'.",
                 "Call db.tool.findMany where label contains q "
                 "(when q is null no where filter).",
                 "Return NextResponse.json with tools."],
             "responses": [{"status": 200, "shape": {"tools": "Tool[]"}}],
             "calls": ["db.tool.findMany", "NextResponse.json"],
             "uses_invariants": [], "demo_domain": DEMO_ROUTE,
             "probe_seed": 8, "probe_cases": []},
        ],
        "ui": [],
    },
]


def run_arm(model, gates: _GateRunner, pieces, arm: str, archive: Path):
    results = []
    for pi, piece in enumerate(pieces):
        seed_base = 400000 + pi * 300 + (500 if arm == "with-doc" else 0)
        tokens = 0
        resolved = False
        failures: list[str] = []
        doc = None
        for i in range(BUDGET_ATTEMPTS):
            if tokens >= BUDGET_TOKENS:
                break
            if arm == "with-doc":
                doc = docgate.pick_doc(piece.kind, piece.spec, failures)
            prompt = baseline_prompt(piece, "")
            if doc is not None:
                # prepend the clearly-labeled documentation block
                prompt = docgate.doc_block(doc) + "\n" + prompt
            out, usage = model.generate(prompt, max_tokens=420,
                                        seed=seed_base + i * 17,
                                        stochastic=(i % 2 == 1))
            tokens += usage.get("tokens", 0)
            code = prompting.extract_construct(piece.anchor + out,
                                               piece.kind)
            g = gates.structural(piece, code)
            if g["pass"]:
                resolved = True
                break
            failures = g.get("failures", [])
            archive.mkdir(parents=True, exist_ok=True)
            (archive / f"{arm}-{piece.pid}-{i}.json").write_text(
                json.dumps({"prompt": prompt[-2500:],
                            "candidate": code}, indent=1))
        results.append({"piece": piece.pid, "resolved": resolved,
                        "tokens": tokens})
        print(f"  [{arm}] {piece.pid:16s} resolved="
              f"{'Y' if resolved else 'N'} ({tokens} tok)", flush=True)
    return results


def main() -> None:
    from archagent.model import FrozenModel
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    model = FrozenModel(threads=2)
    gates = _GateRunner(WS)

    # build the piece list (skip route-probe-only oracle needs: structural)
    pieces = []
    for t in TASKS:
        ir = taskir_from_dict(t)
        ps = ir.pieces()
        for p in ps:
            if p.kind == "prisma-model":
                p.file = "prisma/schema.prisma"
            pieces.append(p)
    print(f"docgate A/B: {len(pieces)} pieces x 2 arms\n", flush=True)

    # fresh scaffold per arm for prisma pieces
    (WS / "prisma/schema.prisma").write_text(_SCAFFOLD_HEAD)

    without = run_arm(model, gates, pieces, "without-doc", OUT / "gen")
    (WS / "prisma/schema.prisma").write_text(_SCAFFOLD_HEAD)
    with_doc = run_arm(model, gates, pieces, "with-doc", OUT / "gen")

    n_wo = sum(r["resolved"] for r in without)
    n_wi = sum(r["resolved"] for r in with_doc)
    t_wo = sum(r["tokens"] for r in without)
    t_wi = sum(r["tokens"] for r in with_doc)
    decision = {
        "corpus": docgate.CORPUS_VERSION,
        "pieces": [p.pid for p in pieces],
        "without_doc": {"resolved": n_wo, "tokens": t_wo,
                        "detail": without},
        "with_doc": {"resolved": n_wi, "tokens": t_wi, "detail": with_doc},
        "becomes_default": bool(n_wi > n_wo and t_wi <= t_wo),
        "rule": "default ON only if with-doc resolves strictly more "
                "pieces at <= tokens of without-doc",
    }
    (OUT / "decision.json").write_text(json.dumps(decision, indent=1))
    print(f"\nwithout-doc: {n_wo}/{len(pieces)} ({t_wo} tok)")
    print(f"with-doc   : {n_wi}/{len(pieces)} ({t_wi} tok)")
    print(f"becomes default: {decision['becomes_default']}")


if __name__ == "__main__":
    main()
