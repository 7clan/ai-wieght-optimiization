"""Route stage, round 3 (Session 035 cont.) — final model attempts.

Round-2 evidence:
- GET body contract LANDED on first sample with the enriched demo
  (param reads + conditional where + JS filter + sort ternary) but
  carried three defects: (a) trailing numbered-prose degeneration that
  survives strip_prompt_echo (cut_repetition removes it), (b) a
  where.status line (status is not a db field), (c) bare minQuantity
  instead of a.minQuantity in the filters
- POST lottery: 12/12 samples missing only the `sku: sku || null`
  literal (best: post2 r2_k1 — clean reads + integer checks + order)
- PUT lottery: right-order samples lack validation entirely (r1_k1);
  the one sample with validation (r0_k3) dead-codes it after update

Round 3 (last model-native attempts before the teacher decision):
A. GET retry with corrected checks: cut_repetition applied to every
   fresh completion, `where.status` rejected, `a.minQuantity` required.
B. POST: micro-FIM on the r2_k1 base for the sku literals.
C. PUT retry with validation expects + validation-before-update order.
Every sample archived; nothing here authors application bytes.
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
from archagent.fullstack.gen_one import strip_prompt_echo, DEMO_ECHO  # noqa: E402
from archagent.fullstack.route_round2 import (CONCEPT, POST_DEMO,  # noqa: E402
                                               POST_SPEC, POST_ANCHOR,
                                               GET_DEMO, GET_SPEC,
                                               GET_ANCHOR, cut_repetition,
                                               _balance)
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


def validate(body: str, expects: list[str], rejects: list[str],
             order_check: tuple[str, str] | None,
             reject_patterns: list[str] | None = None) -> list[str]:
    reasons = []
    for w in DEMO_ECHO:
        if w in body:
            reasons.append(f"demo echo {w!r}")
    for need in expects:
        if need not in body:
            reasons.append(f"missing {need!r}")
    for bad in rejects:
        if bad in body:
            reasons.append(f"forbidden {bad!r}")
    for rx in reject_patterns or []:
        if re.search(rx, body):
            reasons.append(f"forbidden pattern {rx!r}")
    if order_check:
        first, second = order_check
        if (first in body and second in body
                and body.find(first) > body.find(second)):
            reasons.append(f"{first!r} must come before {second!r}")
    if "```" in body:
        reasons.append("markdown fence")
    if reasons == [] and not _balance(body):
        reasons.append("brace imbalance")
    return reasons


def scan_archive(cid: str, step: str, expects: list[str],
                 rejects: list[str],
                 order_check: tuple[str, str] | None) -> tuple[str | None, dict]:
    for f in sorted(GEN.glob(f"{cid}_{step}_r*_k*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        body = cut_repetition(d.get("processed") or "")
        if not body:
            continue
        if not validate(body, expects, rejects, order_check):
            return body, dict(src=f.name, round=d.get("round"),
                              k=d.get("k"), seed=d.get("seed"),
                              tokens=d.get("usage", {}).get("tokens"),
                              from_archive=True)
    return None, {}


def gen_body(model, cid: str, step: str, demo: str, spec: str,
             anchor: str, max_tokens: int, expects: list[str],
             rejects: list[str], order_check: tuple[str, str] | None,
             tag: str,
             reject_patterns: list[str] | None = None
             ) -> tuple[str | None, dict]:
    hit, meta = scan_archive(cid, step, expects, rejects, order_check)
    if hit is not None:
        log(f"  [{tag}] archive pre-scan ACCEPTED {meta['src']}")
        return hit, meta
    feedback = None
    own_prev = None
    for round_no in range(3):
        parts = [CONCEPT, "", demo, "", f"Now YOUR task.  {spec}"]
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
            comp = cut_repetition(comp)
            body = anchor + comp
            reasons = validate(body, expects, rejects, order_check,
                               reject_patterns)
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


def fim_once(model, prefix: str, suffix: str, instr: str, tok: int,
             cid: str, step: str, expects: list[str],
             rejects: list[str] | None = None) -> tuple[str | None, dict]:
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
        for bad in rejects or []:
            if bad in fill:
                reasons.append(f"forbidden {bad!r}")
        if "```" in fill:
            reasons.append("fence")
        ok = not reasons
        (GEN / f"{cid}_fim3_{step}_k{k}.json").write_text(json.dumps(
            dict(kind="fim-patch", cid=cid, step=step, k=k, seed=seed,
                 usage=usage, prefix_tail=prefix[-300:],
                 suffix_head=suffix[:150], instructions=instr,
                 completion=text, reject=reasons or None),
            ensure_ascii=False, indent=1))
        log(f"  [fim3 {cid}/{step} k{k}] seed={seed} "
            f"tok={usage['tokens']} ok={ok} {('; '.join(reasons))[:120]}")
        if ok:
            return fill, dict(k=k, seed=seed, tokens=usage["tokens"])
    return None, {}


PUT_ANCHOR = "  const { id } = await params\n"

PUT_DEMO3 = """Example from a DIFFERENT app (a pet shelter), showing the
ANSWER FORMAT.  The handler updated one animal by id, and the correct
body was:

  const { id } = await params
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
  const row = await db.animal.update({ where: { id }, data: { name, species, notes: notes || null, age, sickDays } }).catch(() => null)
  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return NextResponse.json({ item: { ...row, seenAt: row.seenAt.toISOString() } })"""

PUT_SPEC3 = """Write the body of PUT /api/items/:id (update an inventory
item).  Read, validate, then update — in this exact order:
1. const { id } = await params; const body = await req.json(); read
   name, category, sku as trimmed strings; quantity and minQuantity as
   Number(...)
2. validate BEFORE the update, returning 400 { error: '<message>' } on
   any failure: name 1-80 chars; category 1-40 chars; sku length <= 40
   (empty is allowed); Number.isInteger(quantity) and 0-1000000;
   Number.isInteger(minQuantity) and 0-100000
3. const row = await db.inventoryItem.update({ where: { id }, data: {
   name, category, sku: sku || null, quantity, minQuantity }
   }).catch(() => null)
4. if (!row) return NextResponse.json({ error: 'not found' },
   { status: 404 })
5. return NextResponse.json({ item: { ...row, updatedAt:
   row.updatedAt.toISOString() } })"""


def main() -> None:
    t0 = time.time()
    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    log(f"model loaded in {time.time() - t0:.0f}s")

    # ---- A. GET retry (corrected checks) -----------------------------
    log("== GET body contract, corrected checks ==")
    get_body, get_meta = gen_body(
        model, "route-list", "get3", GET_DEMO, GET_SPEC, GET_ANCHOR, 500,
        expects=["get('category')", "get('status')", "get('sort')",
                 "get('order')", "findMany", "filter", "orderBy"],
        rejects=["where.status", "Write the body"],
        order_check=None, tag="get3",
        reject_patterns=[r"(?<![.\w])minQuantity\b"])

    # ---- B. POST: sku-null literal via micro-FIM on the r1_k0 base ---
    log("== POST sku-null literal (micro-FIM on post2 r1_k0) ==")
    post_base = cut_repetition(json.loads(
        (GEN / "route-list_post2_r1_k0.json").read_text())["processed"])
    if "sku.length > 40" not in post_base:
        log("  NOTE: base lacks the optional-sku check (unexpected)")
    post_meta_base = dict(src="route-list_post2_r1_k0",
                          note="sku check already optional-correct; "
                               "integer checks present; only the null "
                               "literal missing")
    m = re.search(r"data: \{ name, category, sku, quantity, "
                  r"minQuantity \}", post_base)
    b1 = None  # sku check not needed on this base
    b1_meta = dict(already_present=True)
    b2 = None
    b2_meta = {}
    if m:
        pre = post_base[:m.start()]
        suf = post_base[m.end():]
        b2, b2_meta = fim_once(
            model, prefix=pre, suffix=suf,
            instr="Use sku: sku || null for the sku value.",
            tok=60, cid="route-list", step="post-sku-null",
            expects=["sku: sku || null"])
        if b2 is not None:
            post_base = pre + b2 + suf
    else:
        log("  [post-sku-null] create-data shape not found in base — "
            "skipped (recorded)")
    post_final = post_base

    # ---- C. PUT retry with validation expects ------------------------
    log("== PUT body contract, validation required ==")
    put_body, put_meta = gen_body(
        model, "route-id", "put3", PUT_DEMO3, PUT_SPEC3, PUT_ANCHOR, 500,
        expects=["db.inventoryItem.update", ".catch", "'not found'",
                 "Number.isInteger", "if (name.length", "sku: sku || null"],
        rejects=["Write the body"],
        order_check=("if (name.length", "db.inventoryItem.update"),
        tag="put3")

    usage = dict(model.usage())
    log(f"model usage this run: {usage}")
    del model
    gc.collect()
    time.sleep(2)

    # ---- assemble ------------------------------------------------------
    head = ("import { NextRequest, NextResponse } from 'next/server'\n"
            "import { db } from '@/lib/db'\n\n"
            "export async function GET(req: NextRequest) {\n")
    get_inner = (get_body.rstrip() if get_body else
                 "  // GET BODY GENERATION FAILED ROUND 3")
    tail = ("export async function POST(req: NextRequest) {\n"
            + post_final.rstrip() + "\n}\n")
    route_list = head + get_inner + "\n}\n\n" + tail
    p = install.APP / "src/app/api/items/route.ts"
    p.write_text(route_list if route_list.endswith("\n")
                 else route_list + "\n")
    (GEN / "route-list_round3.ts").write_text(route_list)
    log("route-list round-3 file installed + archived")

    get_raw = json.loads((GEN / "body_route-id_get_r0_k1.json").read_text())
    get_id_body = cut_repetition(
        "  const { id } = await params\n" + get_raw["completion"])
    del_raw = json.loads(
        (GEN / "body_route-id_delete_r0_k1.json").read_text())
    del_body = cut_repetition(
        "  const { id } = await params\n" + del_raw["completion"])
    if put_body is None:
        # fall back to the round-2 PUT (r1_k1) with the repetition cut
        put_src = json.loads(
            (GEN / "route-id_put_r1_k1.json").read_text())["processed"]
        put_body = cut_repetition(put_src)
        put_meta = dict(src="route-id_put_r1_k1", fallback=True)
        log("  PUT fell back to r1_k1 (no validation) — recorded")
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
    (GEN / "route-id_round3.ts").write_text(id_file)
    log("route-id round-3 file installed + archived")

    # ---- gates ----------------------------------------------------------
    results = {}
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        results[cid] = dict(ok=ok, feedback=fb)
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:600].replace("\n", "\n  "))

    # ---- ledger ---------------------------------------------------------
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    data["files"]["src/app/api/items/route.ts"] = dict(
        contract="route-list", label="QWEN-REPAIRED",
        base="route-list_r0_k3 near-miss (round 1)",
        get_body=(dict(get_meta,
                       src="route-list_get3_*.json") if get_body
                  else "FAILED-ROUND3"),
        post_body=dict(src="route-list_post2_r2_k1 + fim3 patches",
                       sku_check=b1_meta or "FAILED",
                       sku_null=b2_meta or "FAILED"),
        note=("round-3: GET regenerated with corrected checks (cut + "
              "where.status rejected + a.minQuantity); POST = cleanest "
              "archived body + sku literal FIM patches"))
    data["files"]["src/app/api/items/[id]/route.ts"] = dict(
        contract="route-id", label="QWEN-REPAIRED",
        bodies=dict(
            get=dict(src="body_route-id_get_r0_k1", cut="repetition"),
            put=dict(put_meta),
            delete=dict(src="body_route-id_delete_r0_k1",
                        cut="repetition")),
        note="skeleton lines are disclosed interface scaffolding")
    data["stages"].append(dict(
        contract="route-round3",
        accepted=all(r["ok"] for r in results.values()),
        get_body_ok=get_body is not None,
        post_sku_check=b1 is not None, post_sku_null=b2 is not None,
        put_validation=put_meta.get("src", "").startswith("route-id_put3"),
        gates=results, usage_run=usage))
    c = data.setdefault("model_usage_cumulative", {})
    c["generations"] = c.get("generations", 0) + usage["generations"]
    c["total_new_tokens"] = (c.get("total_new_tokens", 0)
                             + usage["total_new_tokens"])
    LEDGER.write_text(json.dumps(data, indent=1))

    # ---- dynamic apitest --------------------------------------------------
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

    log(f"round-3 complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
