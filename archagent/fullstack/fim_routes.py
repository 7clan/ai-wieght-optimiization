"""FIM-anchored route construction/repair (Session-032 method).

The plain-completion route stages produced: demo echoes, repetition
loops, documentation prose, and one near-miss (route-list r0_k3).
Native fill-in-the-middle with instructions adjacent to the gap and a
suffix anchor bounding the fill is the method Session 032/034 proved
for this model, and it already repaired the schema (sku nullability)
on the first sampled attempt this session.

route.ts (list): start from the r0_k3 QWEN-ORIGINAL base; FIM-replace
the GET and POST bodies with spec-faithful implementations.
[id]/route.ts: FIM-construct all three handlers incrementally on the
interface-contract skeleton (imports + Params + handler signatures —
the same exact-shape convention as the CSS selector contracts).

Every sample (accepted or rejected) is archived with prompt + seed +
tokens; accepted fills are labeled QWEN-REPAIRED in the ledger.
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
from archagent.fullstack.gen_one import (strip_prompt_echo,  # noqa: E402
                                         trim_to_exports)
from archagent.fullstack.contracts import CONTRACTS  # noqa: E402
from archagent.fullstack.gen_one import build_prompt  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402

GEN = ROOT / "experiments/zai-fullstack/generations"
LEDGER = ROOT / "experiments/zai-fullstack/PROVENANCE.json"

GET_INSTR = """Fill in the body of the GET handler for listing inventory
items. Read the query params from req.nextUrl.searchParams: q,
category, status, sort, order. Build a Prisma where object with ONLY
the defined filters: when q is non-empty match name OR sku with
contains; when category is non-empty and not 'all' match category
exactly; status 'low' means quantity > 0 AND quantity <= minQuantity;
status 'out' means quantity = 0; status 'ok' means quantity >
minQuantity. Build the orderBy object from sort ('name', 'quantity'
or 'updatedAt') and order ('asc' or 'desc'). Assign the findMany
result to a variable named rows."""

POST_INSTR = """Fill in the body of the POST handler for creating an
inventory item. Parse the body with req.json(). Validate: name must
be a trimmed string of 1-80 chars; category must be a trimmed string
of 1-40 chars; sku is optional — a trimmed string of at most 40 chars
where an empty string becomes null; quantity must be an integer
between 0 and 1000000 (use Number.isInteger); minQuantity must be an
integer between 0 and 100000. Any invalid field returns 400 with
{ error: '<message>' }. On success create the item with
db.inventoryItem.create (sku null when absent) and return 201 with
{ item: { ...row, updatedAt: row.updatedAt.toISOString() } }."""

ID_GET_INSTR = """Fill in the body of the GET handler. Await the
params Promise to get id. Look the item up with
db.inventoryItem.findUnique({ where: { id } }). When missing return
404 with { error: 'not found' }. Otherwise return { item: { ...row,
updatedAt: row.updatedAt.toISOString() } }."""

ID_PUT_INSTR = """Fill in the body of the PUT handler. Await params
for id, parse the body with req.json(). Validate exactly like a
create: name trimmed 1-80 chars, category trimmed 1-40 chars, sku
optional trimmed <= 40 chars (empty string becomes null), quantity
integer 0-1000000, minQuantity integer 0-100000. Invalid -> 400 with
{ error: '<message>' }. Then update with db.inventoryItem.update({
where: { id }, data: { name, category, sku, quantity, minQuantity }
}).catch(() => null). When the update returns null return 404 with
{ error: 'not found' }. Otherwise return 200 with { item: { ...row,
updatedAt: row.updatedAt.toISOString() } }."""

ID_DEL_INSTR = """Fill in the body of the DELETE handler. Await
params for id. Delete with db.inventoryItem.delete({ where: { id }
}).then(() => true).catch(() => false). When it returns false return
404 with { error: 'not found' }. Otherwise return new
NextResponse(null, { status: 204 })."""

ROUTE_LIST_BASE = """import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
"""

ROUTE_LIST_SUFFIX = """  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })
}

export async function POST(req: NextRequest) {
"""

POST_SUFFIX = """  const row = await db.inventoryItem.create({ data: { name, category, sku, quantity, minQuantity } })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })
}
"""

ROUTE_ID_HEAD = """import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

type Params = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: Params) {
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def shim_contract(cid: str) -> dict:
    return next(c for c in CONTRACTS if c["id"] == cid)


def write_ledger(path: str, rec: dict) -> None:
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    data["files"][path] = rec
    LEDGER.write_text(json.dumps(data, indent=1))


def fim_fill(model, cid: str, step: str, prefix: str, suffix: str,
             instr: str, max_tokens: int) -> str | None:
    """One FIM step: up to 3 samples (greedy, then sampled)."""
    for k in range(3):
        seed = k * 1013 or 7
        stochastic = k != 0
        text, usage = model.fim(prefix=prefix, suffix=suffix,
                                instructions=instr,
                                max_tokens=max_tokens, seed=seed,
                                stochastic=stochastic)
        body = text.strip()
        # quick sanity: must contain a db call and balanced braces
        sane = ("db.inventoryItem" in body
                and body.count("{") - body.count("}") == 0
                and "```" not in body)
        (GEN / f"{cid}_fim_{step}_k{k}.json").write_text(json.dumps(dict(
            kind="fim", contract=cid, step=step, k=k, seed=seed,
            usage=usage, prefix=prefix, suffix=suffix,
            instructions=instr, completion=text, sane=sane),
            ensure_ascii=False, indent=1))
        log(f"  [fim {cid}/{step} k{k}] seed={seed} tok={usage['tokens']} "
            f"sane={sane}")
        if sane:
            return body
    return None


def main() -> None:
    devserver.stop_dev()
    time.sleep(1)
    model = FrozenModel(threads=2)

    # ---- route-list: rebuild from the near-miss base via FIM --------
    log("== route-list FIM repair ==")
    get_body = fim_fill(model, "route-list", "get", ROUTE_LIST_BASE,
                        ROUTE_LIST_SUFFIX, GET_INSTR, 400)
    if not get_body:
        log("GET body FIM failed")
        devserver.start_dev()
        return
    post_body = fim_fill(
        model, "route-list", "post",
        ROUTE_LIST_BASE + get_body + "\n}\n\nexport async function POST"
        "(req: NextRequest) {\n",
        "}\n", POST_INSTR, 450)
    if not post_body:
        log("POST body FIM failed")
        devserver.start_dev()
        return
    file_body = (ROUTE_LIST_BASE + get_body + "\n}\n\n"
                 "export async function POST(req: NextRequest) {\n"
                 + post_body + "\n}\n")
    target = install.APP / "src/app/api/items/route.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file_body)
    contract = shim_contract("route-list")
    ok, fb = runner_d.run_gates(contract, True)
    log(f"route-list gates: ok={ok} fb={fb[:200]}")
    if ok:
        write_ledger("src/app/api/items/route.ts", dict(
            contract="route-list", label="QWEN-REPAIRED",
            note=("r0_k3 base was a near-miss; GET and POST bodies "
                  "re-generated by FIM fills (see generations/"
                  "route-list_fim_*.json)")))

    # ---- route-id: construct all three handlers via FIM -------------
    log("== route-id FIM construction ==")
    id_get = fim_fill(model, "route-id", "get", ROUTE_ID_HEAD, "}\n",
                      ID_GET_INSTR, 300)
    if not id_get:
        log("route-id GET FIM failed")
        devserver.start_dev()
        return
    put_prefix = (ROUTE_ID_HEAD + id_get + "\n}\n\n"
                  "export async function PUT(req: NextRequest, "
                  "{ params }: Params) {\n")
    id_put = fim_fill(model, "route-id", "put", put_prefix, "}\n",
                      ID_PUT_INSTR, 450)
    if not id_put:
        log("route-id PUT FIM failed")
        devserver.start_dev()
        return
    del_prefix = (put_prefix + id_put + "\n}\n\n"
                  "export async function DELETE(_req: NextRequest, "
                  "{ params }: Params) {\n")
    id_del = fim_fill(model, "route-id", "delete", del_prefix, "}\n",
                      ID_DEL_INSTR, 250)
    if not id_del:
        log("route-id DELETE FIM failed")
        devserver.start_dev()
        return
    file_body = (del_prefix + id_del + "\n}\n")
    target = install.APP / "src/app/api/items/[id]/route.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(file_body)
    contract = shim_contract("route-id")
    ok, fb = runner_d.run_gates(contract, True)
    log(f"route-id gates: ok={ok} fb={fb[:200]}")
    if ok:
        write_ledger("src/app/api/items/[id]/route.ts", dict(
            contract="route-id", label="QWEN-REPAIRED",
            note=("constructed handler-by-handler with FIM fills on "
                  "the interface-contract skeleton; see generations/"
                  "route-id_fim_*.json")))

    # ---- final: the frozen API suite --------------------------------
    log("== apitest (frozen, full) ==")
    results = runner_d.dynamic_gates(["apitest"])
    log(json.dumps(results["apitest"]["tail"], indent=1))
    devserver.start_dev()


if __name__ == "__main__":
    main()
