"""SESSION 038A — PHASE 2a: the NEW frozen retest suite.

Three domains, disjoint from every previous suite/curriculum domain
(TaskFlow, MediVault, StockPilot, RoomReserve, courier, approvals,
maintenance, pricing, greenhouse, and all curriculum vocabularies
Band/Album/Plot/Planting/Screen/Showing/Customer/Coupon/Category/
Aisle/Bin/Ferry/Vet/Pen/Stable/Library/Folder):

  1. orchard  — harvest tracking (state-transition invariant)
  2. marina   — berth booking   (interval-overlap invariant — the
                hardest 036/037 class)
  3. bakery   — oven batches    (numeric double-bound invariant)

Per domain: 2 prisma-model pieces + 1 invariant + 2 route pieces
(GET search-filter + POST multi-branch validation — the two universal
Session-037 gap families) = 5 pieces; 15 total.

Demos reuse the fixed Session-037 example vocabulary (Vet pair /
pipeline-stage / ferry-capacity / spa-route): the DOMAINS are what is
new; the demo law is unchanged (matching contract definitions with the
037 comparison).

FREEZE DISCIPLINE: running this module records the suite sha256 in
experiments/z038a-independent-retest/suite/MANIFEST.json.  It must be
recorded BEFORE any model generation against the suite.  The manifest
check refuses to run if the hash drifts after freeze.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "experiments/z038a-independent-retest/suite"

# ---------------------------------------------------------------- demos
VET_PAIR_DEMO = (
    "model Vet {\n"
    "  id        String  @id @default(cuid())\n"
    "  name      String\n"
    "  visits    Visit[]\n"
    "}\n\n"
    "model Visit {\n"
    "  id        String  @id @default(cuid())\n"
    "  title     String\n"
    "  start     String\n"
    "  vetId     String\n"
    "  vet       Vet @relation(fields: [vetId], references: [id])\n"
    "}")

LIFECYCLE_DEMO = (
    "// pipeline stage check (different domain)\n"
    "export function canAdvance(current: string, next: string) {\n"
    "  return (current === 'raw' && next === 'edited') ||\n"
    "         (current === 'edited' && next === 'published')\n"
    "}\n")

INTERVAL_DEMO = (
    "// event hall double-booking check (different domain)\n"
    "export function hallsOverlap(aStart: string, aEnd: string,\n"
    "                             bStart: string, bEnd: string) {\n"
    "  return aStart <= bEnd && bStart <= aEnd\n"
    "}\n")

QUOTA_DEMO = (
    "// ferry crossing capacity check (different domain)\n"
    "export function ferryHasRoom(current: number, capacity: number) {\n"
    "  return current < capacity\n"
    "}\n")

ROUTE_DEMO = (
    "// a hotel spa treatment booking route (different domain)\n"
    "import { NextRequest, NextResponse } from 'next/server'\n"
    "import { db } from '@/lib/db'\n\n"
    "export async function GET(req: NextRequest) {\n"
    "  const guest = req.nextUrl.searchParams.get('guest') ?? ''\n"
    "  const where: { title?: { contains: string } } = {}\n"
    "  if (guest) where.title = { contains: guest }\n"
    "  const rows = await db.treatment.findMany({ where, "
    "orderBy: { start: 'asc' } })\n"
    "  return NextResponse.json({ treatments: rows, total: rows.length })\n"
    "}\n\n"
    "export async function POST(req: NextRequest) {\n"
    "  const body = await req.json()\n"
    "  const title = String(body.title ?? '').trim()\n"
    "  if (!title) {\n"
    "    return NextResponse.json({ error: 'Title is required' }, "
    "{ status: 400 })\n"
    "  }\n"
    "  const suite = await db.suite.findUnique({ where: { id: "
    "body.suiteId } })\n"
    "  if (!suite) {\n"
    "    return NextResponse.json({ error: 'Suite not found' }, "
    "{ status: 404 })\n"
    "  }\n"
    "  const created = await db.treatment.create({\n"
    "    data: { suiteId: suite.id, title, start: body.start },\n"
    "  })\n"
    "  return NextResponse.json({ treatment: created }, { status: 201 })\n"
    "}\n")

# ================================================================ domain 1
ORCHARD = {
    "app": "orchard",
    "concept": ("OrchardOps: harvest tracking for a fruit orchard. "
                "Trees are recorded per plot; staff log harvests per "
                "tree and move each tree through growing -> ripe -> "
                "picked stages."),
    "entities": [
        {"pid": "or-tree", "name": "Tree",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "variety", "type": "String"},
             {"name": "plantedYear", "type": "Int"},
             {"name": "plot", "type": "String"}],
         "relations": [
             {"name": "harvests", "target": "Harvest",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "or-harvest", "name": "Harvest",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "kg", "type": "Int"},
             {"name": "pickedAt", "type": "String"},
             {"name": "treeId", "type": "String"}],
         "relations": [
             {"name": "tree", "target": "Tree",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "treeId"}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "or-stage",
         "statement": ("canMoveStage is true exactly for the valid next "
                       "stages growing -> ripe and ripe -> picked. Every "
                       "other transition is invalid, including staying "
                       "in the same stage."),
         "signature": "canMoveStage(current: string, next: string)",
         "ref_expr": "(current === 'growing' && next === 'ripe') || "
                     "(current === 'ripe' && next === 'picked')",
         "cases": [
             {"name": "growing-to-ripe",
              "inputs": ["growing", "ripe"], "expect": True},
             {"name": "ripe-to-picked",
              "inputs": ["ripe", "picked"], "expect": True},
             {"name": "skip", "inputs": ["growing", "picked"],
              "expect": False},
             {"name": "backwards",
              "inputs": ["ripe", "growing"], "expect": False},
             {"name": "same", "inputs": ["ripe", "ripe"],
              "expect": False}],
         "demo_domain": LIFECYCLE_DEMO},
    ],
    "routes": [
        {"pid": "or-get", "method": "GET", "path": "/api/trees",
         "file": "src/app/api/trees/route.ts",
         "clauses": [
             "Export GET. Read variety from searchParams.",
             "Build where object with variety contains when variety is set.",
             "Call db.tree.findMany with where ordered by variety asc, "
             "include harvests relation.",
             "Return NextResponse.json with trees and total."],
         "responses": [{"status": 200, "shape": {"trees": "list",
                                                 "total": "number"}}],
         "calls": ["db.tree.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "tree",
              "data": {"id": "seed-tree-1", "variety": "Gala",
                        "plantedYear": 2019, "plot": "North"}},
             {"model": "tree",
              "data": {"id": "seed-tree-2", "variety": "Fuji",
                        "plantedYear": 2021, "plot": "South"}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["trees", "total"],
              "json_contains": ["Gala", "Fuji"]},
             {"name": "filter-variety", "params": {"variety": "ala"},
              "expect_status": 200, "json_contains": ["Gala"]}]},
        {"pid": "or-post", "method": "POST", "path": "/api/harvests",
         "file": "src/app/api/harvests/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Validate kg with Number; when not between 1 and 2000 "
             "return 400 'Kg must be 1-2000'.",
             "Call db.tree.findUnique where id body.treeId; when missing "
             "return 404 'Tree not found'.",
             "Call db.harvest.create with data kg, pickedAt, treeId.",
             "Return NextResponse.json with harvest and status 201."],
         "responses": [
             {"status": 400, "message": "Kg must be 1-2000", "shape": {}},
             {"status": 404, "message": "Tree not found", "shape": {}},
             {"status": 201, "shape": {"harvest": "Harvest"}}],
         "calls": ["db.tree.findUnique", "db.harvest.create",
                   "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "tree",
              "data": {"id": "seed-tree-3", "variety": "Pink",
                        "plantedYear": 2015, "plot": "East"}}],
         "probe_cases": [
             {"name": "kg-zero",
              "body": {"kg": 0, "treeId": "seed-tree-3"},
              "expect_status": 400, "json_contains": ["Kg must be 1-2000"]},
             {"name": "kg-over",
              "body": {"kg": 5000, "treeId": "seed-tree-3"},
              "expect_status": 400},
             {"name": "unknown-tree",
              "body": {"kg": 40, "treeId": "no-such-tree"},
              "expect_status": 404,
              "json_contains": ["Tree not found"]},
             {"name": "valid-create",
              "body": {"kg": 40, "treeId": "seed-tree-3",
                        "pickedAt": "2026-10-01"},
              "expect_status": 201, "json_keys": ["harvest"]}]},
    ],
    "ui": [],
}

# ================================================================ domain 2
MARINA = {
    "app": "marina",
    "concept": ("HarborDesk: berth booking for a boat marina. Berths "
                "are recorded per dock; most bookings reserve a berth, "
                "but transient bookings without a berth are allowed."),
    "entities": [
        {"pid": "ma-berth", "name": "Berth",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "code", "type": "String"},
             {"name": "lengthM", "type": "Int"}],
         "relations": [
             {"name": "bookings", "target": "Booking",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "ma-booking", "name": "Booking",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "vessel", "type": "String"},
             {"name": "start", "type": "String"},
             {"name": "end", "type": "String"},
             {"name": "berthId", "type": "String", "optional": True}],
         "relations": [
             {"name": "berth", "target": "Berth",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "berthId", "optional": True}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "ma-overlap",
         "statement": ("bookingsOverlap is true exactly when two booking "
                       "windows [aStart, aEnd] and [bStart, bEnd] overlap "
                       "at any point (touching endpoints counts as "
                       "overlap)."),
         "signature": "bookingsOverlap(aStart: string, aEnd: string, "
                      "bStart: string, bEnd: string)",
         "ref_expr": "aStart <= bEnd && bStart <= aEnd",
         "cases": [
             {"name": "identical",
              "inputs": ["2026-07-01", "2026-07-05",
                         "2026-07-01", "2026-07-05"], "expect": True},
             {"name": "partial",
              "inputs": ["2026-07-01", "2026-07-05",
                         "2026-07-04", "2026-07-09"], "expect": True},
             {"name": "touching",
              "inputs": ["2026-07-01", "2026-07-05",
                         "2026-07-05", "2026-07-09"], "expect": True},
             {"name": "disjoint",
              "inputs": ["2026-07-01", "2026-07-05",
                         "2026-07-06", "2026-07-09"], "expect": False},
             {"name": "nested",
              "inputs": ["2026-07-01", "2026-07-10",
                         "2026-07-03", "2026-07-04"], "expect": True}],
         "demo_domain": INTERVAL_DEMO},
    ],
    "routes": [
        {"pid": "ma-get", "method": "GET", "path": "/api/bookings",
         "file": "src/app/api/bookings/route.ts",
         "clauses": [
             "Export GET. Read vessel from searchParams.",
             "Build where object with vessel contains when vessel is set.",
             "Call db.booking.findMany with where ordered by start asc, "
             "include berth relation.",
             "Return NextResponse.json with bookings and total."],
         "responses": [{"status": 200, "shape": {"bookings": "list",
                                                 "total": "number"}}],
         "calls": ["db.booking.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "booking",
              "data": {"id": "seed-booking-1", "vessel": "Selene",
                        "start": "2026-07-01", "end": "2026-07-05"}},
             {"model": "booking",
              "data": {"id": "seed-booking-2", "vessel": "Adriana",
                        "start": "2026-07-10", "end": "2026-07-12"}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["bookings", "total"],
              "json_contains": ["Selene", "Adriana"]},
             {"name": "filter-vessel", "params": {"vessel": "ele"},
              "expect_status": 200, "json_contains": ["Selene"]}]},
        {"pid": "ma-post", "method": "POST", "path": "/api/bookings",
         "file": "src/app/api/bookings/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Trim vessel with String; when empty return 400 "
             "'Vessel is required'.",
             "When body.berthId is provided call db.berth.findUnique "
             "where id body.berthId; when missing return 404 "
             "'Berth not found'.",
             "Call db.booking.create with data vessel, start, end and "
             "berthId only when provided.",
             "Return NextResponse.json with booking and status 201."],
         "responses": [
             {"status": 400, "message": "Vessel is required", "shape": {}},
             {"status": 404, "message": "Berth not found", "shape": {}},
             {"status": 201, "shape": {"booking": "Booking"}}],
         "calls": ["db.berth.findUnique", "db.booking.create",
                   "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "berth",
              "data": {"id": "seed-berth-1", "code": "D-04",
                        "lengthM": 12}}],
         "probe_cases": [
             {"name": "missing-vessel",
              "body": {"start": "2026-07-01", "end": "2026-07-05"},
              "expect_status": 400,
              "json_contains": ["Vessel is required"]},
             {"name": "unknown-berth",
              "body": {"vessel": "Selene", "berthId": "no-such-berth",
                        "start": "2026-07-01", "end": "2026-07-05"},
              "expect_status": 404,
              "json_contains": ["Berth not found"]},
             {"name": "valid-transient",
              "body": {"vessel": "Selene",
                        "start": "2026-08-01", "end": "2026-08-03"},
              "expect_status": 201, "json_keys": ["booking"]},
             {"name": "valid-with-berth",
              "body": {"vessel": "Adriana", "berthId": "seed-berth-1",
                        "start": "2026-08-01", "end": "2026-08-03"},
              "expect_status": 201, "json_keys": ["booking"]}]},
    ],
    "ui": [],
}

# ================================================================ domain 3
BAKERY = {
    "app": "bakery",
    "concept": ("KneadOps: wholesale bakery batch tracking. Ovens are "
                "recorded with a maximum load; batches start in the "
                "proofing stage and must fit the oven's capacity."),
    "entities": [
        {"pid": "ba-oven", "name": "Oven",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "name", "type": "String"},
             {"name": "maxLoad", "type": "Int"}],
         "relations": [
             {"name": "batches", "target": "Batch",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "ba-batch", "name": "Batch",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "dough", "type": "String"},
             {"name": "loadKg", "type": "Int"},
             {"name": "status", "type": "String",
              "attrs": ["@default(\"proofing\")"]},
             {"name": "ovenId", "type": "String"}],
         "relations": [
             {"name": "oven", "target": "Oven",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "ovenId"}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "ba-proof",
         "statement": ("isProofTempOk is true exactly when celsius is "
                       "at least 18 and at most 26 (both inclusive)."),
         "signature": "isProofTempOk(celsius: number)",
         "ref_expr": "celsius >= 18 && celsius <= 26",
         "cases": [
             {"name": "below", "inputs": [17.9], "expect": False},
             {"name": "min-boundary", "inputs": [18], "expect": True},
             {"name": "mid", "inputs": [22], "expect": True},
             {"name": "max-boundary", "inputs": [26], "expect": True},
             {"name": "above", "inputs": [26.1], "expect": False}],
         "demo_domain": QUOTA_DEMO},
    ],
    "routes": [
        {"pid": "ba-get", "method": "GET", "path": "/api/batches",
         "file": "src/app/api/batches/route.ts",
         "clauses": [
             "Export GET. Read status from searchParams.",
             "Build where object with status equals when status is set.",
             "Call db.batch.findMany with where ordered by dough asc, "
             "include oven relation.",
             "Return NextResponse.json with batches and total."],
         "responses": [{"status": 200, "shape": {"batches": "list",
                                                 "total": "number"}}],
         "calls": ["db.batch.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "batch",
              "data": {"id": "seed-batch-1", "dough": "Rye",
                        "loadKg": 30, "status": "proofing"}},
             {"model": "batch",
              "data": {"id": "seed-batch-2", "dough": "Wheat",
                        "loadKg": 45, "status": "baked"}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["batches", "total"],
              "json_contains": ["Rye", "Wheat"]},
             {"name": "filter-status", "params": {"status": "proofing"},
              "expect_status": 200, "json_contains": ["Rye"]}]},
        {"pid": "ba-post", "method": "POST", "path": "/api/batches",
         "file": "src/app/api/batches/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Validate loadKg with Number; when not at least 1 return "
             "400 'Load must be positive'.",
             "Call db.oven.findUnique where id body.ovenId; when missing "
             "return 404 'Oven not found'.",
             "Call db.batch.create with data dough, loadKg, ovenId and "
             "status defaulting to proofing.",
             "Return NextResponse.json with batch and status 201."],
         "responses": [
             {"status": 400, "message": "Load must be positive",
              "shape": {}},
             {"status": 404, "message": "Oven not found", "shape": {}},
             {"status": 201, "shape": {"batch": "Batch"}}],
         "calls": ["db.oven.findUnique", "db.batch.create",
                   "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [
             {"model": "oven",
              "data": {"id": "seed-oven-1", "name": "Deck 2",
                        "maxLoad": 60}}],
         "probe_cases": [
             {"name": "load-zero",
              "body": {"dough": "Rye", "loadKg": 0, "ovenId": "seed-oven-1"},
              "expect_status": 400,
              "json_contains": ["Load must be positive"]},
             {"name": "unknown-oven",
              "body": {"dough": "Rye", "loadKg": 20,
                        "ovenId": "no-such-oven"},
              "expect_status": 404,
              "json_contains": ["Oven not found"]},
             {"name": "valid-create",
              "body": {"dough": "Rye", "loadKg": 20,
                        "ovenId": "seed-oven-1"},
              "expect_status": 201, "json_keys": ["batch"]}]},
    ],
    "ui": [],
}

DOMAINS = [ORCHARD, MARINA, BAKERY]


def manifest() -> dict:
    h = hashlib.sha256()
    for d in DOMAINS:
        h.update(json.dumps(d, sort_keys=True).encode())
    return {"suite_sha256": h.hexdigest(),
            "n_domains": len(DOMAINS),
            "n_pieces": sum(2 + 1 + 2 for _ in DOMAINS),
            "frozen_before_generation": True,
            "frozen_at_commit": "SESSION038A Phase 2a"}


if __name__ == "__main__":
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    m = manifest()
    p = SUITE_DIR / "MANIFEST.json"
    if p.exists():
        old = json.loads(p.read_text())
        if old["suite_sha256"] != m["suite_sha256"]:
            raise SystemExit(
                "FROZEN RETEST SUITE MODIFIED after freeze!\n"
                f"  committed: {old['suite_sha256'][:16]}\n"
                f"  current:   {m['suite_sha256'][:16]}\n"
                "Disclose the change or restore the original.")
        print("manifest matches (unchanged since freeze)")
    else:
        p.write_text(json.dumps(m, indent=1))
        print("FROZEN:", json.dumps(m, indent=1))
    (SUITE_DIR / "suite.json").write_text(
        json.dumps(DOMAINS, indent=1), encoding="utf-8")
