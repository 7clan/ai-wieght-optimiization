"""Body-granularity generation for the route files (Session 035).

Plain-completion contracts at HANDLER-BODY granularity — the size at
which this model reliably produces real code (types.ts, route-list
r0_k3).  Each body is generated from an exact-shape prompt (concept +
different-domain demo + compact action spec + anchor), then the file
is assembled mechanically: skeleton + bodies.  Gates: tsc, eslint,
required exports, then the full frozen apitest.

FIM with long instructions was tried and rejected (instruction echo —
archived as route-list_fim_get_k*.json); FIM remains validated for
MICRO patches only (schema sku fix).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.fullstack import runner_d  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402
from archagent.fullstack.gen_one import (strip_prompt_echo,  # noqa: E402
                                         trim_to_exports, quick_reject)

GEN = ROOT / "experiments/zai-fullstack/generations"
LEDGER = ROOT / "experiments/zai-fullstack/PROVENANCE.json"

CONCEPT = """You write TypeScript handler bodies for Next.js API routes
with Prisma.  The handler signature and imports are already written.
Write only the body: plain statements, no comments, no TODOs, return
a NextResponse in every path."""

DEMO_BODY = """Example from a DIFFERENT app (a pet shelter), showing the
ANSWER FORMAT.  The handler was "list animals, filtered", and the
correct body was:

  const sp = req.nextUrl.searchParams
  const q = sp.get('q')?.trim().toLowerCase() ?? ''
  const kind = sp.get('kind') ?? 'all'
  const where: { OR?: { name: { contains: string } }[]; kind?: string } = {}
  if (q) where.OR = [{ name: { contains: q } }]
  if (kind && kind !== 'all') where.kind = kind
  const rows = await db.animal.findMany({ where, orderBy: { name: 'asc' } })
  const items = rows.map((r) => ({ ...r, seenAt: r.seenAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })"""

GET_SPEC = """Write the body of GET /api/items (list inventory items):
1. const sp = req.nextUrl.searchParams; read q, category, status,
   sort (default 'updatedAt'), order (default 'desc')
2. build a where object: q non-empty -> OR: [name contains q, sku
   contains q]; category non-empty and not 'all' -> category: value;
   status 'low' -> AND: [quantity > 0, quantity <= minQuantity];
   status 'out' -> quantity: 0; status 'ok' -> quantity >
   minQuantity (use the exact property names quantity and
   minQuantity in the AND array items like { quantity: { gt: 0 } })
3. const rows = await db.inventoryItem.findMany({ where, orderBy: {
   [sort]: order } })
4. const items = rows.map((r) => ({ ...r, updatedAt:
   r.updatedAt.toISOString() })); return NextResponse.json({ items,
   total: items.length })"""

POST_SPEC = """Write the body of POST /api/items (create an item):
1. const body = await req.json(); const name =
   String(body.name ?? '').trim(); const category =
   String(body.category ?? '').trim(); const sku =
   String(body.sku ?? '').trim(); const quantity =
   Number(body.quantity); const minQuantity = Number(body.minQuantity)
2. validate and return 400 { error: '<message>' } on any failure:
   name 1-80 chars; category 1-40 chars; sku length <= 40 (sku stays
   an empty string for now); Number.isInteger(quantity) && 0-1000000;
   Number.isInteger(minQuantity) && 0-100000
3. const row = await db.inventoryItem.create({ data: { name,
   category, sku: sku || null, quantity, minQuantity } })
4. return NextResponse.json({ item: { ...row, updatedAt:
   row.updatedAt.toISOString() } }, { status: 201 })"""

ID_GET_SPEC = """Write the body of GET /api/items/:id:
1. const { id } = await params
2. const row = await db.inventoryItem.findUnique({ where: { id } })
3. if (!row) return NextResponse.json({ error: 'not found' },
   { status: 404 })
4. return NextResponse.json({ item: { ...row, updatedAt:
   row.updatedAt.toISOString() } })"""

ID_PUT_SPEC = """Write the body of PUT /api/items/:id (update an item):
1. const { id } = await params; const body = await req.json();
   read name, category, sku, quantity, minQuantity exactly like a
   create (trim strings, Number for the ints, sku may be empty)
2. validate exactly like create (name 1-80, category 1-40, sku <= 40,
   Number.isInteger(quantity) 0-1000000, Number.isInteger(minQuantity)
   0-100000); any failure -> 400 { error: '<message>' }
3. const row = await db.inventoryItem.update({ where: { id }, data: {
   name, category, sku: sku || null, quantity, minQuantity }
   }).catch(() => null)
4. if (!row) return 404 { error: 'not found' }; else return
   NextResponse.json({ item: { ...row, updatedAt:
   row.updatedAt.toISOString() } })"""

ID_DEL_SPEC = """Write the body of DELETE /api/items/:id:
1. const { id } = await params
2. const ok = await db.inventoryItem.delete({ where: { id }
   }).then(() => true).catch(() => false)
3. if (!ok) return NextResponse.json({ error: 'not found' },
   { status: 404 })
4. return new NextResponse(null, { status: 204 })"""

LIST_HEAD = """import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
"""
LIST_MID = """
}

export async function POST(req: NextRequest) {
"""
ID_HEAD = """import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

type Params = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: Params) {
"""
ID_MID1 = """
}

export async function PUT(req: NextRequest, { params }: Params) {
"""
ID_MID2 = """
}

export async function DELETE(_req: NextRequest, { params }: Params) {
"""
TAIL = """
}
"""

BODIES = [
    dict(cid="route-list", step="get", spec=GET_SPEC,
         anchor="  const sp = req.nextUrl.searchParams\n",
         max_tokens=420),
    dict(cid="route-list", step="post", spec=POST_SPEC,
         anchor="  const body = await req.json()\n", max_tokens=420),
    dict(cid="route-id", step="get", spec=ID_GET_SPEC,
         anchor="  const { id } = await params\n", max_tokens=250),
    dict(cid="route-id", step="put", spec=ID_PUT_SPEC,
         anchor="  const { id } = await params\n", max_tokens=450),
    dict(cid="route-id", step="delete", spec=ID_DEL_SPEC,
         anchor="  const { id } = await params\n", max_tokens=250),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def gen_body(model, b: dict, feedback: str | None,
             own_prev: str | None) -> str | None:
    parts = [CONCEPT, "", DEMO_BODY, "",
             f"Now YOUR task.  {b['spec']}"]
    if own_prev:
        parts.append("")
        parts.append("Your previous body (which failed the checks) was:")
        parts.append(own_prev[-800:])
    if feedback:
        parts.append("")
        parts.append("The automated checks reported:")
        parts.append(feedback[-700:])
        parts.append("Fix exactly that.")
    parts.append("")
    parts.append("Write the body now.  The first line is already "
                 "written; continue from it:")
    parts.append(b["anchor"])
    prompt = "\n".join(parts)
    for round_no in range(3):
        for k in range(4):
            seed = (k * 1013 + round_no * 77) or 7
            stochastic = k != 0
            text, usage = model.generate(prompt, max_tokens=b["max_tokens"],
                                         seed=seed, stochastic=stochastic)
            comp = strip_prompt_echo(text.strip("\n"), prompt)
            body = b["anchor"].rstrip("\n") + "\n" + comp
            reason = quick_reject(comp, b["anchor"])
            sane = (reason is None and "db.inventoryItem" in body
                    and "NextResponse" in body)
            (GEN / f"body_{b['cid']}_{b['step']}_r{round_no}_k{k}.json"
             ).write_text(json.dumps(dict(
                kind="body", contract=b["cid"], step=b["step"],
                round=round_no, k=k, seed=seed, usage=usage,
                prompt=prompt, completion=text, processed=body,
                reject=reason, sane=sane), ensure_ascii=False, indent=1))
            log(f"  [body {b['cid']}/{b['step']} r{round_no} k{k}] "
                f"seed={seed} tok={usage['tokens']} reject={reason} "
                f"sane={sane}")
            if sane:
                return body
        # feed the last failure back for the next round
        fb = f"last sample rejected: {reason}"
        parts_fb = [CONCEPT, "", DEMO_BODY, "", f"Now YOUR task.  {b['spec']}",
                    "", "The automated checks reported:", fb,
                    "Fix exactly that.", "",
                    "Write the body now.  The first line is already "
                    "written; continue from it:", b["anchor"]]
        prompt = "\n".join(parts_fb)
    return None


def write_ledger(path: str, rec: dict) -> None:
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    data["files"][path] = rec
    data["stages"].append(dict(contract=f"{rec['contract']}:bodies",
                               accepted=True))
    LEDGER.write_text(json.dumps(data, indent=1))


def main() -> None:
    devserver.stop_dev()
    time.sleep(1)
    model = FrozenModel(threads=2)
    results = {}
    for b in BODIES:
        log(f"== body {b['cid']}/{b['step']} ==")
        body = gen_body(model, b, None, None)
        if not body:
            log(f"BODY FAILED: {b['cid']}/{b['step']}")
            results[b["step"]] = None
            devserver.start_dev()
            return
        results[b["step"]] = body

    # assemble route-list
    file_body = (LIST_HEAD + results["get"].rstrip() + LIST_MID
                 + results["post"].rstrip() + TAIL)
    p = install.APP / "src/app/api/items/route.ts"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(file_body + "\n")
    # assemble route-id
    file_body = (ID_HEAD + results["get"].rstrip() + ID_MID1
                 + results["put"].rstrip() + ID_MID2
                 + results["delete"].rstrip() + TAIL)
    p = install.APP / "src/app/api/items/[id]/route.ts"
    p.write_text(file_body + "\n")

    from archagent.fullstack.contracts import CONTRACTS
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        log(f"{cid} gates: ok={ok} fb={fb[:300]}")
        if ok:
            write_ledger(contract["file"], dict(
                contract=cid, label="QWEN-REPAIRED",
                note=("handler bodies generated at body-granularity "
                      "contracts (generations/body_*.json); file "
                      "assembled mechanically from the interface "
                      "skeleton")))

    log("== apitest (frozen, full) ==")
    res = runner_d.dynamic_gates(["apitest"])
    log(json.dumps(res["apitest"]["tail"], indent=1))
    devserver.start_dev()


if __name__ == "__main__":
    main()
