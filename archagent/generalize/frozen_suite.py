"""SESSION 037 — PHASE 9: the FROZEN evaluation suite.

Three domains, deliberately disjoint from TaskFlow / MediVault /
StockPilot / RoomReserve / courier / curriculum domains:

  1. approvals   — permit-request workflow (state transitions + FK)
  2. maintenance — machine / maintenance-log relational records
  3. pricing     — plan / subscription quota rules

Per domain: 2 prisma-model pieces + 1 invariant piece + 2 route pieces
= 5 pieces; 15 pieces total.  Every invariant carries a frozen case
table + reference oracle; every route carries frozen probe cases
(self-seeding: they exercise the route's own POST/GET contract).

FREEZE DISCIPLINE: this file's content hash is recorded in
experiments/z037-generalization/frozen-suite/MANIFEST.json at commit
time, BEFORE any model generation against it.  Any post-freeze edit is
a disclosed compromise, not a silent fix.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITE_DIR = ROOT / "experiments" / "z037-generalization" / "frozen-suite"

# ---------------------------------------------------------------- demos
# All demos are VET-domain (consistent with the curricula — a fixed,
# frozen example vocabulary the model has seen throughout development;
# the DOMAINS of the tasks are what is new).

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
APPROVALS = {
    "app": "approvals",
    "concept": ("PermitFlow: a permit-request approval workflow. "
                "Requests move draft -> review -> approved or rejected; "
                "each request is reviewed by a registered approver."),
    "entities": [
        {"pid": "ap-approver", "name": "Approver",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "name", "type": "String"},
             {"name": "email", "type": "String"}],
         "relations": [
             {"name": "requests", "target": "Request",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "ap-request", "name": "Request",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "title", "type": "String"},
             {"name": "status", "type": "String",
              "attrs": ["@default(\"draft\")"]},
             {"name": "approverId", "type": "String"}],
         "relations": [
             {"name": "approver", "target": "Approver",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "approverId"}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "ap-transition",
         "statement": ("canAdvanceRequest is true exactly for the valid "
                       "next steps draft -> review, review -> approved, "
                       "review -> rejected. Every other transition is "
                       "invalid, including staying in the same state."),
         "signature": "canAdvanceRequest(current: string, next: string)",
         "ref_expr": "(current === 'draft' && next === 'review') || (current === 'review' && next === 'approved') || (current === 'review' && next === 'rejected')",
         "cases": [
             {"name": "draft-to-review", "inputs": ["draft", "review"], "expect": True},
             {"name": "review-to-approved", "inputs": ["review", "approved"], "expect": True},
             {"name": "review-to-rejected", "inputs": ["review", "rejected"], "expect": True},
             {"name": "skip", "inputs": ["draft", "approved"], "expect": False},
             {"name": "backwards", "inputs": ["review", "draft"], "expect": False},
             {"name": "same", "inputs": ["draft", "draft"], "expect": False}],
         "demo_domain": LIFECYCLE_DEMO},
    ],
    "routes": [
        {"pid": "ap-post", "method": "POST", "path": "/api/requests",
         "file": "src/app/api/requests/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Trim title with String; when empty return 400 'Title is required'.",
             "Call db.approver.findUnique where id body.approverId; when missing return 404 'Approver not found'.",
             "When body.status is set and canAdvanceRequest('draft', body.status) is false return 400 'Invalid status'.",
             "Call db.request.create with data title, status 'draft', approverId.",
             "Return NextResponse.json with request and status 201."],
         "responses": [
             {"status": 400, "message": "Title is required", "shape": {}},
             {"status": 404, "message": "Approver not found", "shape": {}},
             {"status": 201, "shape": {"request": "Request"}}],
         "calls": ["db.approver.findUnique", "db.request.create",
                   "NextResponse.json"],
         "uses_invariants": ["ap-transition"],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "approver",
                          "data": {"id": "seed-approver-1",
                                    "name": "Dana Reed",
                                    "email": "dana@example.com"}}],
         "probe_cases": [
             {"name": "missing-title", "body": {"approverId": "seed-approver-1"},
              "expect_status": 400, "json_contains": ["Title is required"]},
             {"name": "unknown-approver",
              "body": {"title": "New deck permit", "approverId": "no-such-id"},
              "expect_status": 404, "json_contains": ["Approver not found"]},
             {"name": "valid-create",
              "body": {"title": "New deck permit",
                        "approverId": "seed-approver-1"},
              "expect_status": 201, "json_keys": ["request"]}]},
        {"pid": "ap-get", "method": "GET", "path": "/api/requests",
         "file": "src/app/api/requests/route.ts",
         "clauses": [
             "Export GET. Read q and status from searchParams.",
             "Build where object with title contains when q is set.",
             "When status is set add status equals to where.",
             "Call db.request.findMany with where ordered by title asc.",
             "Return NextResponse.json with requests and total."],
         "responses": [{"status": 200, "shape": {"requests": "list",
                                                  "total": "number"}}],
         "calls": ["db.request.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "request",
                          "data": {"id": "seed-request-1",
                                    "title": "Fence permit",
                                    "status": "draft",
                                    "approverId": "seed-approver-1"}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["requests", "total"]},
             {"name": "filter-status",
              "params": {"status": "draft"},
              "expect_status": 200, "json_contains": ["Fence permit"]},
             {"name": "filter-status-empty",
              "params": {"status": "approved"},
              "expect_status": 200,
              "json_keys": ["requests", "total"]}]},
    ],
    "ui": [],
}

# ================================================================ domain 2
MAINTENANCE = {
    "app": "maintenance",
    "concept": ("ServiceDesk: equipment maintenance records. Machines "
                "own maintenance logs; each log records what was done "
                "and when."),
    "entities": [
        {"pid": "mn-machine", "name": "Machine",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "name", "type": "String"},
             {"name": "location", "type": "String"}],
         "relations": [
             {"name": "logs", "target": "Log",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "mn-log", "name": "Log",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "summary", "type": "String"},
             {"name": "performedAt", "type": "String"},
             {"name": "machineId", "type": "String"}],
         "relations": [
             {"name": "machine", "target": "Machine",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "machineId"}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "mn-window",
         "statement": ("logWithinPeriod is true exactly when performed "
                       "lies within the reporting period (both bounds "
                       "inclusive)."),
         "signature": "logWithinPeriod(performed: string, from: string, to: string)",
         "ref_expr": "from <= performed && performed <= to",
         "cases": [
             {"name": "inside", "inputs": ["2026-03-10", "2026-03-01", "2026-03-31"], "expect": True},
             {"name": "touching-from", "inputs": ["2026-03-01", "2026-03-01", "2026-03-31"], "expect": True},
             {"name": "touching-to", "inputs": ["2026-03-31", "2026-03-01", "2026-03-31"], "expect": True},
             {"name": "before", "inputs": ["2026-02-20", "2026-03-01", "2026-03-31"], "expect": False},
             {"name": "after", "inputs": ["2026-04-02", "2026-03-01", "2026-03-31"], "expect": False}],
         "demo_domain": ("// broadcast slot containment (different domain)\n"
                         "export function slotInside(showStart: string, "
                         "showEnd: string,\n"
                         "                           dayStart: string, "
                         "dayEnd: string) {\n"
                         "  return dayStart <= showStart && showEnd <= "
                         "dayEnd\n}\n")},
    ],
    "routes": [
        {"pid": "mn-post", "method": "POST", "path": "/api/logs",
         "file": "src/app/api/logs/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Trim summary with String; when empty return 400 'Summary is required'.",
             "Call db.machine.findUnique where id body.machineId; when missing return 404 'Machine not found'.",
             "Call db.log.create with data summary, performedAt, machineId.",
             "Return NextResponse.json with log and status 201."],
         "responses": [
             {"status": 400, "message": "Summary is required", "shape": {}},
             {"status": 404, "message": "Machine not found", "shape": {}},
             {"status": 201, "shape": {"log": "Log"}}],
         "calls": ["db.machine.findUnique", "db.log.create",
                   "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "machine",
                          "data": {"id": "seed-machine-1",
                                    "name": "Press A",
                                    "location": "Bay 1"}}],
         "probe_cases": [
             {"name": "missing-summary", "body": {"machineId": "seed-machine-1"},
              "expect_status": 400, "json_contains": ["Summary is required"]},
             {"name": "unknown-machine",
              "body": {"summary": "Replaced belt",
                        "machineId": "no-such-id"},
              "expect_status": 404, "json_contains": ["Machine not found"]},
             {"name": "valid-create",
              "body": {"summary": "Replaced belt",
                        "performedAt": "2026-03-10",
                        "machineId": "seed-machine-1"},
              "expect_status": 201, "json_keys": ["log"]}]},
        {"pid": "mn-get", "method": "GET", "path": "/api/machines",
         "file": "src/app/api/machines/route.ts",
         "clauses": [
             "Export GET. Read q from searchParams.",
             "Build where object with name contains when q is set.",
             "Call db.machine.findMany with where ordered by name asc, include logs relation.",
             "Return NextResponse.json with machines and total."],
         "responses": [{"status": 200, "shape": {"machines": "list",
                                                  "total": "number"}}],
         "calls": ["db.machine.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "machine",
                          "data": {"id": "seed-machine-2",
                                    "name": "Lathe B",
                                    "location": "Bay 2"}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["machines", "total"]},
             {"name": "filter-q",
              "params": {"q": "Lathe"}, "expect_status": 200,
              "json_contains": ["Lathe B"]}]},
    ],
    "ui": [],
}

# ================================================================ domain 3
PRICING = {
    "app": "pricing",
    "concept": ("MeterBox: subscription pricing with quotas. Plans carry "
                "a usage limit; subscriptions consume units against "
                "their plan's limit."),
    "entities": [
        {"pid": "pr-plan", "name": "Plan",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "name", "type": "String"},
             {"name": "limit", "type": "Int"}],
         "relations": [
             {"name": "subscriptions", "target": "Subscription",
              "kind": "one-to-many", "is_list": True}],
         "demo_domain": VET_PAIR_DEMO},
        {"pid": "pr-subscription", "name": "Subscription",
         "fields": [
             {"name": "id", "type": "String",
              "attrs": ["@id", "@default(cuid())"]},
             {"name": "owner", "type": "String"},
             {"name": "used", "type": "Int",
              "attrs": ["@default(0)"]},
             {"name": "planId", "type": "String"}],
         "relations": [
             {"name": "plan", "target": "Plan",
              "kind": "many-to-one", "is_list": False,
              "fk_field": "planId"}],
         "demo_domain": VET_PAIR_DEMO},
    ],
    "invariants": [
        {"pid": "pr-quota",
         "statement": ("withinQuota is true exactly when used is at "
                       "most the limit (equal means still within)."),
         "signature": "withinQuota(used: number, limit: number)",
         "ref_expr": "used <= limit",
         "cases": [
             {"name": "under", "inputs": [3, 10], "expect": True},
             {"name": "exactly-at-limit", "inputs": [10, 10], "expect": True},
             {"name": "over", "inputs": [11, 10], "expect": False},
             {"name": "zero", "inputs": [0, 0], "expect": True}],
         "demo_domain": QUOTA_DEMO},
    ],
    "routes": [
        {"pid": "pr-post", "method": "POST", "path": "/api/subscriptions",
         "file": "src/app/api/subscriptions/route.ts",
         "clauses": [
             "Export POST. Await req.json.",
             "Trim owner with String; when empty return 400 'Owner is required'.",
             "Call db.plan.findUnique where id body.planId; when missing return 404 'Plan not found'.",
             "Call db.subscription.create with data owner, used 0, planId.",
             "Return NextResponse.json with subscription and status 201."],
         "responses": [
             {"status": 400, "message": "Owner is required", "shape": {}},
             {"status": 404, "message": "Plan not found", "shape": {}},
             {"status": 201, "shape": {"subscription": "Subscription"}}],
         "calls": ["db.plan.findUnique", "db.subscription.create",
                   "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "plan",
                          "data": {"id": "seed-plan-1", "name": "Starter",
                                    "limit": 100}}],
         "probe_cases": [
             {"name": "missing-owner", "body": {"planId": "seed-plan-1"},
              "expect_status": 400, "json_contains": ["Owner is required"]},
             {"name": "unknown-plan",
              "body": {"owner": "Acme Corp", "planId": "no-such-id"},
              "expect_status": 404, "json_contains": ["Plan not found"]},
             {"name": "valid-create",
              "body": {"owner": "Acme Corp", "planId": "seed-plan-1"},
              "expect_status": 201, "json_keys": ["subscription"]}]},
        {"pid": "pr-get", "method": "GET", "path": "/api/plans",
         "file": "src/app/api/plans/route.ts",
         "clauses": [
             "Export GET. Read maxLimit from searchParams.",
             "Call db.plan.findMany ordered by name asc.",
             "Filter plans by limit at most maxLimit when it is above zero.",
             "Return NextResponse.json with plans and total."],
         "responses": [{"status": 200, "shape": {"plans": "list",
                                                  "total": "number"}}],
         "calls": ["db.plan.findMany", "NextResponse.json"],
         "uses_invariants": [],
         "demo_domain": ROUTE_DEMO,
         "probe_seed": [{"model": "plan",
                          "data": {"id": "seed-plan-2", "name": "Basic",
                                    "limit": 100}},
                         {"model": "plan",
                          "data": {"id": "seed-plan-3", "name": "Pro",
                                    "limit": 1000}}],
         "probe_cases": [
             {"name": "list-all", "expect_status": 200,
              "json_keys": ["plans", "total"]},
             {"name": "filter-maxlimit",
              "params": {"maxLimit": "500"}, "expect_status": 200,
              "json_contains": ["Basic"]}]},
    ],
    "ui": [],
}

DOMAINS = [APPROVALS, MAINTENANCE, PRICING]


def manifest() -> dict:
    """Content hash of the frozen suite (recomputed; must MATCH the
    committed MANIFEST.json — any drift is a disclosed edit)."""
    h = hashlib.sha256()
    for d in DOMAINS:
        h.update(json.dumps(d, sort_keys=True).encode())
    return {"suite_sha256": h.hexdigest(),
            "n_domains": len(DOMAINS),
            "n_pieces": sum(2 + 1 + 2 for _ in DOMAINS),
            "frozen_before_generation": True}


if __name__ == "__main__":
    SUITE_DIR.mkdir(parents=True, exist_ok=True)
    m = manifest()
    p = SUITE_DIR / "MANIFEST.json"
    if p.exists():
        old = json.loads(p.read_text())
        if old["suite_sha256"] != m["suite_sha256"]:
            raise SystemExit(
                "FROZEN SUITE MODIFIED after freeze!\n"
                f"  committed: {old['suite_sha256'][:16]}\n"
                f"  current:   {m['suite_sha256'][:16]}\n"
                "Disclose the change or restore the original.")
        print("manifest matches (unchanged since freeze)")
    else:
        p.write_text(json.dumps(m, indent=1))
        print("FROZEN:", json.dumps(m, indent=1))
