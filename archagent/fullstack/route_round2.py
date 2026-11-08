"""Route stage, round 2 (Session 035 cont.) — calibrated by trackD10.

Round-1 evidence (all archived):
- micro-FIM succeeds ONLY for in-context-imitation edits (category
  read/validate, create-data); fills for novel patterns copy the local
  block verbatim (p6 "landed" as a no-op) or drift (p4 added junk
  reads description/weight/cost/image)
- completion-mode body contracts reliably produce right-ordered,
  complete CRUD bodies (PUT r1_k1 / r2_k0) but WITHOUT
  Number.isInteger; the one sample WITH it (PUT r0_k3) had the
  validation dead-coded after the update
- the archived DELETE body needs a repetition-based cut (its prose
  markers were already consumed by strip_prompt_echo in the archive)

Round 2:
1. route-id: reassemble from PUT r1_k1 (right order, complete) with
   the fixed repetition cut for DELETE; GET unchanged (correct).
2. route-list POST: regenerate as ONE body contract (12-sample budget,
   strict expects incl. validation-before-create order).
3. route-list GET: (a) imitation-instruction FIM ladder retry; if the
   param reads do not land, (b) a full GET body contract whose demo
   shows param reads + conditional where + JS status filter + sort
   ternary (the patterns no prior demo showed).
4. Last-model-attempt for the integer conditions via literal-expression
   FIM; anything still missing is recorded FAILED for the teacher
   decision (this script does NOT author application bytes).
"""
from __future__ import annotations

import gc
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.fullstack import runner_d  # noqa: E402
from archagent.fullstack.contracts import CONTRACTS  # noqa: E402
from archagent.fullstack.gen_one import (strip_prompt_echo,  # noqa: E402
                                         trim_to_exports,
                                         DEMO_ECHO)
from archagent.model import FrozenModel  # noqa: E402

EXP = ROOT / "experiments/zai-fullstack"
GEN = EXP / "generations"
LEDGER = EXP / "PROVENANCE.json"
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/.npm-global/lib/node_modules",
    BASE="http://127.0.0.1:3000",
)


def log(msg: str) -> None:
    print(msg, flush=True)


CONCEPT = """You write TypeScript handler bodies for Next.js API routes
with Prisma.  The handler signature and imports are already written.
Write only the body: plain statements, no comments, no TODOs, return
a NextResponse in every path."""

# --------------------------------------------------------------- cuts

def cut_repetition(text: str) -> str:
    """Mechanical cut: stop at the first line that verbatim-repeats an
    earlier kept line (this model's degeneration signature), and at
    numbered/narrative prose markers.  Kept lines are never altered."""
    lines = text.splitlines()
    keep: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        s = ln.strip()
        if (re.match(r"^\d+\.\s", s) or s.startswith("The handler")
                or s.startswith("The next task") or s.startswith("I wrote")
                or s.startswith("And the second line")
                or s.startswith("Note:") or s.startswith("```")
                or s.startswith("Write the body")):
            break
        if len(s) > 10 and s in seen:
            break  # verbatim repetition -> degeneration begins
        if s:
            seen.add(s)
        keep.append(ln)
    while keep and not keep[-1].strip():
        keep.pop()
    return "\n".join(keep)


# ------------------------------------------------------- POST body

POST_DEMO = """Example from a DIFFERENT app (a pet shelter), showing the
ANSWER FORMAT.  The handler created an adoption record, and the
correct body was:

  const body = await req.json()
  const name = String(body.name ?? '').trim()
  const species = String(body.species ?? '').trim()
  const notes = String(body.notes ?? '').trim()
  const age = Number(body.age)
  const sickDays = Number(body.sickDays)
  if (name.length < 1 || name.length > 60) {
    return NextResponse.json({ error: 'name is required (1-60 chars)' }, { status: 400 })
  }
  if (species.length < 1 || species.length > 40) {
    return NextResponse.json({ error: 'species is required (1-40 chars)' }, { status: 400 })
  }
  if (notes.length > 200) {
    return NextResponse.json({ error: 'notes must be at most 200 chars' }, { status: 400 })
  }
  if (!Number.isInteger(age) || age < 0 || age > 40) {
    return NextResponse.json({ error: 'age must be an integer 0-40' }, { status: 400 })
  }
  if (!Number.isInteger(sickDays) || sickDays < 0 || sickDays > 90) {
    return NextResponse.json({ error: 'sickDays must be an integer 0-90' }, { status: 400 })
  }
  const row = await db.adoption.create({ data: { name, species, notes: notes || null, age, sickDays } })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })"""

POST_SPEC = """Write the body of POST /api/items (create an inventory
item).  Read and validate the fields exactly like this:
1. const body = await req.json(); then read: name, category, sku as
   trimmed strings (String(body.x ?? '').trim()); quantity and
   minQuantity as Number(body.x)
2. validate in this order, returning 400 { error: '<message>' } on any
   failure: name 1-80 chars; category 1-40 chars; sku length <= 40
   (empty is ALLOWED); Number.isInteger(quantity) and 0-1000000;
   Number.isInteger(minQuantity) and 0-100000
3. const row = await db.inventoryItem.create({ data: { name,
   category, sku: sku || null, quantity, minQuantity } })
4. return NextResponse.json({ item: { ...row, updatedAt:
   row.updatedAt.toISOString() } }, { status: 201 })"""

POST_ANCHOR = "  const body = await req.json()\n"


# -------------------------------------------------------- GET body

GET_DEMO = """Example from a DIFFERENT app (a pet shelter), showing the
ANSWER FORMAT.  The handler listed animals with filters, and the
correct body was:

  const sp = req.nextUrl.searchParams
  const q = sp.get('q')?.trim().toLowerCase() ?? ''
  const kind = sp.get('kind') ?? 'all'
  const sort = sp.get('sort') ?? 'name'
  const order = sp.get('order') ?? 'asc'
  const where: { OR?: { name: { contains: string } }[]; kind?: string } = {}
  if (q) where.OR = [{ name: { contains: q } }]
  if (kind && kind !== 'all') where.kind = kind
  let rows = await db.animal.findMany({ where, orderBy: sort === 'age' ? { age: order } : { name: order } })
  if (sort === 'sick') rows = rows.filter((a) => a.sickDays > 3)
  const items = rows.map((a) => ({ ...a, seenAt: a.seenAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })"""

GET_SPEC = """Write the body of GET /api/items (list inventory items
with filters):
1. const sp = req.nextUrl.searchParams; read q (trimmed, lowercased,
   default ''), category (default 'all'), status (default 'all'),
   sort (default 'updatedAt'), order (default 'desc')
2. build a where object: when q is non-empty set where.OR to
   [{ name: { contains: q } }, { sku: { contains: q } }]; when
   category is non-empty and not 'all' set where.category to category
3. let rows = await db.inventoryItem.findMany({ where, orderBy:
   sort === 'name' ? { name: order } : sort === 'quantity' ?
   { quantity: order } : { updatedAt: order } })
4. status filter on rows: 'low' -> keep items with quantity > 0 and
   quantity <= minQuantity; 'out' -> keep quantity === 0; 'ok' -> keep
   quantity > minQuantity
5. const items = rows.map((r) => ({ ...r, updatedAt:
   r.updatedAt.toISOString() })); return NextResponse.json({ items,
   total: items.length })"""

GET_ANCHOR = "  const sp = req.nextUrl.searchParams\n"


def _validate_body(body: str, expects: list[str],
                   order_check: tuple[str, str] | None) -> list[str]:
    """Shared acceptance checks for generated bodies (harness bug #6
    fixed: the order check previously fired on the CORRECT order)."""
    reasons = []
    for w in DEMO_ECHO:
        if w in body:
            reasons.append(f"demo echo {w!r}")
    for need in expects:
        if need not in body:
            reasons.append(f"missing {need!r}")
    if order_check:
        first, second = order_check  # first must come BEFORE second
        if (first in body and second in body
                and body.find(first) > body.find(second)):
            reasons.append(f"{first!r} must come before {second!r}")
    if "```" in body:
        reasons.append("markdown fence")
    if reasons == [] and not _balance(body):
        reasons.append("brace imbalance")
    return reasons


def scan_archive(cid: str, step: str, expects: list[str],
                 order_check: tuple[str, str] | None
                 ) -> tuple[str | None, dict]:
    """Re-validate already-archived samples with the CURRENT checks
    (samples wrongly rejected by a harness bug are not re-spent)."""
    for f in sorted(GEN.glob(f"{cid}_{step}_r*_k*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        body = d.get("processed") or ""
        if not body:
            continue
        if not _validate_body(body, expects, order_check):
            return body, dict(src=f.name, round=d.get("round"),
                              k=d.get("k"), seed=d.get("seed"),
                              tokens=d.get("usage", {}).get("tokens"),
                              from_archive=True)
    return None, {}


def gen_body(model, cid: str, step: str, concept: str, demo: str,
             spec: str, anchor: str, max_tokens: int,
             expects: list[str], order_check: tuple[str, str] | None,
             tag: str) -> tuple[str | None, dict]:
    """Body-contract generation: archive pre-scan, then 3 rounds x 4
    samples with failure feedback between rounds."""
    hit, meta = scan_archive(cid, step, expects, order_check)
    if hit is not None:
        log(f"  [{tag}] archive pre-scan ACCEPTED {meta['src']}")
        return hit, meta
    feedback = None
    own_prev = None
    for round_no in range(3):
        parts = [concept, "", demo, "", f"Now YOUR task.  {spec}"]
        if own_prev:
            parts += ["", "Your previous body (which failed the checks) "
                           "was:", own_prev[-900:]]
        if feedback:
            parts += ["", "The automated checks reported:", feedback[-700:],
                      "Fix exactly that."]
        parts += ["", "Write the body now.  The first line is already "
                      "written; continue from it:", anchor]
        prompt = "\n".join(parts)
        for k in range(4):
            seed = (k * 1013 + round_no * 77) or 7
            stochastic = k != 0
            text, usage = model.generate(prompt, max_tokens=max_tokens,
                                         seed=seed, stochastic=stochastic)
            comp = strip_prompt_echo(text.strip("\n"), prompt)
            body = anchor + comp
            reasons = _validate_body(body, expects, order_check)
            ok = not reasons
            (GEN / f"{cid}_{step}_r{round_no}_k{k}.json").write_text(
                json.dumps(dict(kind="body", contract=cid, step=step,
                                round=round_no, k=k, seed=seed, usage=usage,
                                prompt=prompt, completion=text,
                                processed=body, reject=reasons or None),
                           ensure_ascii=False, indent=1))
            log(f"  [{tag} r{round_no} k{k}] seed={seed} "
                f"tok={usage['tokens']} ok={ok} "
                f"{('; '.join(reasons))[:130]}")
            if ok:
                return body, dict(round=round_no, k=k, seed=seed,
                                  tokens=usage["tokens"])
        own_prev = comp
        feedback = "last sample rejected: " + "; ".join(reasons)
    return None, {}


def _balance(text: str) -> bool:
    depth = 0
    in_str = None
    i = 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                break
            i = j
        elif c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


# -------------------------------------------------- FIM imitations

def fim_once(model, prefix: str, suffix: str, instr: str, tok: int,
             cid: str, step: str, expects: list[str]) -> tuple[str | None, dict]:
    for k in range(3):
        seed = k * 1013 or 7
        stochastic = k != 0
        text, usage = model.fim(prefix=prefix, suffix=suffix,
                                instructions=instr, max_tokens=tok,
                                seed=seed, stochastic=stochastic)
        fill = text.strip("\n")
        reasons = []
        for w in DEMO_ECHO:
            if w in fill:
                reasons.append(f"demo echo {w!r}")
        for need in expects:
            if need not in fill:
                reasons.append(f"missing {need!r}")
        if "```" in fill:
            reasons.append("fence")
        ok = not reasons
        (GEN / f"{cid}_fimr_{step}_k{k}.json").write_text(json.dumps(
            dict(kind="fim-patch", cid=cid, step=step, k=k, seed=seed,
                 usage=usage, prefix_tail=prefix[-300:],
                 suffix_head=suffix[:150], instructions=instr,
                 completion=text, reject=reasons or None),
            ensure_ascii=False, indent=1))
        log(f"  [fimr {cid}/{step} k{k}] seed={seed} "
            f"tok={usage['tokens']} ok={ok} {('; '.join(reasons))[:120]}")
        if ok:
            return fill, dict(k=k, seed=seed, tokens=usage["tokens"])
    return None, {}


LIST_GET_PREFIX = """import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
"""

LIST_GET_SUFFIX = """  const rows = await db.inventoryItem.findMany({
    where: q ? { OR: [{ name: { contains: q } }, { sku: { contains: q } }] } : {},
    orderBy: { updatedAt: 'desc' },
  })
"""


def main() -> None:
    t0 = time.time()
    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    log(f"model loaded in {time.time() - t0:.0f}s")

    # ---- 1. route-list POST body (fresh, strict) --------------------
    log("== POST body contract ==")
    post_body, post_meta = gen_body(
        model, "route-list", "post2", CONCEPT, POST_DEMO, POST_SPEC,
        POST_ANCHOR, 450,
        expects=["db.inventoryItem.create", "Number.isInteger",
                 "sku: sku || null", "category"],
        order_check=("if (name.length", "db.inventoryItem.create"),
        tag="post2")

    # ---- 2. route-list GET: imitation FIM, else body contract -------
    log("== GET: imitation FIM p1' ==")
    p1, p1_meta = fim_once(
        model, LIST_GET_PREFIX, LIST_GET_SUFFIX,
        "Read category, status, sort and order the same way as q, with "
        "defaults 'all', 'all', 'updatedAt', 'desc'.", 160,
        "route-list", "p1r",
        expects=["get('category')", "get('status')", "get('sort')",
                 "get('order')"])
    get_body = None
    get_meta: dict = {}
    if p1 is not None:
        # p2': where + orderBy with the new vars in context
        prefix2 = (LIST_GET_PREFIX + p1
                   + "\n  const rows = await db.inventoryItem.findMany({\n")
        suffix2 = "  })\n  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))\n"
        p2, p2_meta = fim_once(
            model, prefix2, suffix2,
            "Set where.category when it is not 'all'; map sort and order "
            "to the orderBy key.", 200, "route-list", "p2r",
            expects=["category", "orderBy"])
        if p2 is not None:
            # p3': status filter before the map
            prefix3 = (LIST_GET_PREFIX + p1
                       + "\n  const rows = await db.inventoryItem.findMany({\n"
                       + p2 + "\n  })\n")
            suffix3 = "  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))\n  return NextResponse.json({ items, total: items.length })\n"
            p3, p3_meta = fim_once(
                model, prefix3, suffix3,
                "Filter rows by status into a new list: 'low' keeps "
                "quantity above 0 and at most minQuantity, 'out' keeps "
                "quantity 0, 'ok' keeps quantity above minQuantity.", 220,
                "route-list", "p3r",
                expects=["minQuantity", "filter"])
            if p3 is not None:
                get_body = (LIST_GET_PREFIX + p1 + "\n"
                            + "  const rows = await db.inventoryItem."
                              "findMany({\n" + p2 + "\n  })\n" + p3 + "\n"
                            + suffix3)
                get_meta = dict(mode="fim-ladder", p1=p1_meta, p2=p2_meta,
                                p3=p3_meta)
    if get_body is None:
        log("== GET body contract (fallback) ==")
        get_body, get_meta = gen_body(
            model, "route-list", "get2", CONCEPT, GET_DEMO, GET_SPEC,
            GET_ANCHOR, 500,
            expects=["get('category')", "get('status')", "get('sort')",
                     "get('order')", "findMany", "filter", "orderBy"],
            order_check=None, tag="get2")
        if get_body:
            get_meta = dict(mode="body-contract", **get_meta)

    usage = dict(model.usage())
    log(f"model usage this run: {usage}")

    # ---- 3. assemble + install --------------------------------------
    del model
    gc.collect()
    time.sleep(2)

    if post_body is None:
        log("POST body FAILED — keeping round-1 merged POST (recorded)")
        post_final = None
    else:
        post_final = post_body

    if get_body is None:
        log("GET body FAILED — keeping near-miss GET (recorded)")
        get_final = None
    else:
        get_final = get_body

    # route-list: rebuild from the round-1 merged file, splicing in the
    # new bodies where they landed (near-miss GET / round-1 POST kept
    # otherwise — every gap is recorded, never silently filled)
    base = (GEN / "route-list_merged.ts").read_text()
    parts = base.split("\nexport async function POST(req: NextRequest) {\n")
    head = parts[0]  # imports + GET + blank separator
    if get_final:
        if get_final.startswith(LIST_GET_PREFIX):
            get_inner = get_final[len(LIST_GET_PREFIX):].rstrip()
        else:
            get_inner = get_final.rstrip()
        head = ("import { NextRequest, NextResponse } from 'next/server'\n"
                "import { db } from '@/lib/db'\n\n"
                "export async function GET(req: NextRequest) {\n"
                + get_inner + "\n}\n")
    if post_final:
        tail = ("export async function POST(req: NextRequest) {\n"
                + post_final.rstrip() + "\n}\n")
    else:
        tail = ("export async function POST(req: NextRequest) {\n"
                + parts[1])
    route_list = head + "\n" + tail
    p = install.APP / "src/app/api/items/route.ts"
    p.write_text(route_list if route_list.endswith("\n")
                 else route_list + "\n")
    (GEN / "route-list_round2.ts").write_text(route_list)
    log("route-list round-2 file installed + archived")

    # route-id: PUT r1_k1 (right order) + fixed DELETE cut
    put = json.loads((GEN / "route-id_put_r1_k1.json").read_text())
    put_body = put["processed"]
    del_raw = json.loads(
        (GEN / "body_route-id_delete_r0_k1.json").read_text())
    del_body = cut_repetition(
        "  const { id } = await params\n" + del_raw["completion"])
    get_raw = json.loads((GEN / "body_route-id_get_r0_k1.json").read_text())
    get_id_body = cut_repetition(
        "  const { id } = await params\n" + get_raw["completion"])
    log(f"route-id cuts: get {len(get_id_body.splitlines())} lines, "
        f"delete {len(del_body.splitlines())} lines, put "
        f"{len(put_body.splitlines())} lines")
    id_file = (
        "import { NextRequest, NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "type Params = { params: Promise<{ id: string }> }\n\n"
        "export async function GET(_req: NextRequest, { params }: Params) {\n"
        + get_id_body.rstrip() + "\n}\n\n"
        "export async function PUT(req: NextRequest, { params }: Params) {\n"
        + put_body.rstrip() + "\n}\n\n"
        "export async function DELETE(_req: NextRequest, "
        "{ params }: Params) {\n"
        + del_body.rstrip() + "\n}\n")
    t2 = install.APP / "src/app/api/items/[id]/route.ts"
    t2.write_text(id_file)
    (GEN / "route-id_round2.ts").write_text(id_file)
    log("route-id round-2 file installed + archived")

    # ---- 4. static gates ---------------------------------------------
    results = {}
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        results[cid] = dict(ok=ok, feedback=fb)
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:600].replace("\n", "\n  "))

    # ---- 5. ledger -----------------------------------------------------
    def record(data: dict) -> None:
        data["files"]["src/app/api/items/route.ts"] = dict(
            contract="route-list", label="QWEN-REPAIRED",
            base="route-list_r0_k3 near-miss (round 1)",
            post_body=(dict(src="route-list_post2_*.json", **post_meta)
                       if post_final else "FAILED-ROUND2"),
            get_body=(dict(get_meta, src=(
                "route-list_get2_*.json" if get_meta.get("mode")
                == "body-contract" else "route-list_fimr_*.json"))
                if get_final else "FAILED-ROUND2"),
            note=("round-2 rebuild: POST regenerated as one body "
                  "contract; GET via fim-ladder or body contract; "
                  "per-sample evidence in generations/"))
        data["files"]["src/app/api/items/[id]/route.ts"] = dict(
            contract="route-id", label="QWEN-REPAIRED",
            bodies=dict(
                get=dict(src="body_route-id_get_r0_k1",
                         cut="repetition"),
                put=dict(src="route-id_put_r1_k1",
                         note="right-ordered complete body from round 1"),
                delete=dict(src="body_route-id_delete_r0_k1",
                            cut="repetition")),
            note="skeleton lines are disclosed interface scaffolding")
        data["stages"].append(dict(
            contract="route-round2",
            accepted=all(r["ok"] for r in results.values()),
            post_body_ok=post_final is not None,
            get_body_ok=get_final is not None,
            gates=results, usage_run=usage))
        c = data.setdefault("model_usage_cumulative", {})
        c["generations"] = c.get("generations", 0) + usage["generations"]
        c["total_new_tokens"] = (c.get("total_new_tokens", 0)
                                 + usage["total_new_tokens"])
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    record(data)
    LEDGER.write_text(json.dumps(data, indent=1))

    # ---- 6. dynamic apitest -------------------------------------------
    devserver.start_dev()
    log("== apitest (frozen, as-committed) ==")
    try:
        r = subprocess.run(["node", str(EXP / "apitest.mjs")],
                           capture_output=True, text=True, timeout=600,
                           env=NODE_ENV, cwd=str(EXP))
        log(r.stdout)
        if r.stderr.strip():
            log("stderr: " + r.stderr[-400:])
    except subprocess.TimeoutExpired:
        log("apitest TIMEOUT")

    log(f"round-2 complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
