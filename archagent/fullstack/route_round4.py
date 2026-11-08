"""Route stage, round 4 (Session 035 cont.) — surgical FIM finals.

Round-3 outcome: both route files pass tsc/eslint/exports; apitest
6/16 (POST complete incl. legit integer checks; id-routes work; PUT
persists via the validation-free r1_k1 fallback).  Remaining gaps,
each now a single named defect on a known base:

  GET  (get3 r0_k1 body):  (a) where.status line (invalid field)
                           (b) bare minQuantity in filters
  PUT  (put3 r0_k0 body):  (c) sku check rejects empty (must be
                           optional), (d) no Number.isInteger x2,
                           (e) bare sku in update data
  POST (post2 r1_k0 body): (f) bare sku in create data

This runner attempts each as a micro-FIM patch with a literal
instruction (the schema-repair format).  Whatever fails its 3-sample
budget is reported FAILED-FOR-TEACHER — this module never authors
application bytes.
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
from archagent.fullstack.gen_one import DEMO_ECHO  # noqa: E402
from archagent.fullstack.route_round2 import cut_repetition, _balance  # noqa: E402
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


def patch(model, base: str, pid: str, start: str, end: str, instr: str,
          tok: int, expects: list[str], rejects: list[str] | None = None,
          max_lines: int = 6, allow_empty: bool = False
          ) -> tuple[str | None, dict]:
    """Replace the gap between `start` and `end` (unique substrings of
    base) with a model FIM fill."""
    i = base.find(start)
    j = base.find(end, i + len(start))
    if i == -1 or j == -1:
        log(f"  [{pid}] anchors not found in base — skipped (recorded)")
        return None, dict(error="anchors-missing")
    prefix, suffix = base[:i + len(start)], base[j:]
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
        if len(fill.splitlines()) > max_lines:
            reasons.append("too long")
        if not allow_empty and not fill.strip():
            reasons.append("empty")
        cand = prefix + fill + ("\n" if fill and not fill.endswith("\n")
                                else "") + suffix
        if reasons == [] and not _balance(cand):
            reasons.append("imbalance")
        ok = not reasons
        (GEN / f"r4_{pid}_k{k}.json").write_text(json.dumps(
            dict(kind="fim-patch", pid=pid, k=k, seed=seed, usage=usage,
                 instructions=instr, completion=text,
                 reject=reasons or None), ensure_ascii=False, indent=1))
        log(f"  [r4 {pid} k{k}] seed={seed} tok={usage['tokens']} "
            f"ok={ok} {('; '.join(reasons))[:110]}")
        if ok:
            return cand, dict(k=k, seed=seed, tokens=usage["tokens"])
    return None, {}


def main() -> None:
    t0 = time.time()
    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    log(f"model loaded in {time.time() - t0:.0f}s")

    meta: dict = {}

    # ---------------- GET: patch the best get3 sample -----------------
    get_body = cut_repetition(json.loads(
        (GEN / "route-list_get3_r0_k1.json").read_text())["processed"])
    log(f"GET base (get3 r0_k1, cut): {len(get_body.splitlines())} lines")

    # (a) remove the where.status line (deletion patch: empty fill)
    ws = "  if (status && status !== 'all') where.status = status\n"
    if ws in get_body:
        pre = get_body[:get_body.find(ws)]
        suf = get_body[get_body.find(ws) + len(ws):]
        # manual FIM call with allow-empty semantics
        for k in range(3):
            seed = k * 1013 or 7
            text, usage = model.fim(
                prefix=pre, suffix=suf,
                instructions="Delete this line: status is not a "
                             "database field.",
                max_tokens=30, seed=seed, stochastic=k != 0)
            fill = text.strip("\n")
            ok = (not fill.strip()
                  or ("where.status" not in fill
                      and len(fill.splitlines()) <= 1))
            (GEN / f"r4_get-drop-where-status_k{k}.json").write_text(
                json.dumps(dict(kind="fim-patch", pid="get-drop-where"
                                "-status", k=k, seed=seed, usage=usage,
                                instructions="Delete this line: status "
                                "is not a database field.",
                                completion=text,
                                reject=None if ok else "fill not empty/"
                                "clean"), ensure_ascii=False, indent=1))
            log(f"  [r4 get-drop-where-status k{k}] seed={seed} "
                f"tok={usage['tokens']} ok={ok} fill={fill[:40]!r}")
            if ok:
                get_body = pre + fill + ("\n" if fill.strip() else "") + suf
                meta["get_drop_where_status"] = dict(
                    k=k, seed=seed, tokens=usage["tokens"],
                    empty=not fill.strip())
                break
        else:
            meta["get_drop_where_status"] = "FAILED-FOR-TEACHER"
    else:
        meta["get_drop_where_status"] = "not-in-base"

    # (b) a.minQuantity in the filters
    if "a.minQuantity" not in get_body and "minQuantity" in get_body:
        fl_start = "  if (status === 'low')"
        fl_end = "  const items = rows.map"
        new_get, m_b = patch(
            model, get_body, "get-a-minquantity",
            start=fl_start, end=fl_end,
            instr="Use a.minQuantity in the comparisons.",
            tok=160, expects=["a.minQuantity"],
            rejects=None, max_lines=4)
        if new_get:
            get_body = new_get
            meta["get_a_minquantity"] = m_b
        else:
            meta["get_a_minquantity"] = "FAILED-FOR-TEACHER"
    else:
        meta["get_a_minquantity"] = "already-ok"

    # ---------------- PUT: patch put3 r0_k0 ----------------------------
    put_body = json.loads(
        (GEN / "route-id_put3_r0_k0.json").read_text())["processed"]

    # (c) sku check -> optional
    sku_start = "  if (sku.length < 1 || sku.length > 40) {\n"
    sku_end = "  if (quantity < 0 || quantity > 1000000) {"
    new_put, m_c = patch(
        model, put_body, "put-sku-optional",
        start=sku_start, end=sku_end,
        instr="sku is optional: reject only when longer than 40 chars.",
        tok=90, expects=["sku.length > 40"], max_lines=4)
    if new_put:
        put_body = new_put
        meta["put_sku_optional"] = m_c
    else:
        meta["put_sku_optional"] = "FAILED-FOR-TEACHER"

    # (d) integer checks (quantity + minQuantity blocks, one patch each)
    q_start = "  if (quantity < 0 || quantity > 1000000) {\n"
    q_end = "  if (minQuantity < 0 || minQuantity > 1000000) {"
    new_put, m_d = patch(
        model, put_body, "put-quantity-integer",
        start=q_start, end=q_end,
        instr="Use !Number.isInteger(quantity) || in the condition.",
        tok=90, expects=["Number.isInteger"], max_lines=4)
    if new_put:
        put_body = new_put
        meta["put_quantity_integer"] = m_d
    else:
        meta["put_quantity_integer"] = "FAILED-FOR-TEACHER"

    if "Number.isInteger(minQuantity" not in put_body:
        m_start = "  if (minQuantity < 0 || minQuantity > 1000000) {\n"
        m_end = "  const row = await db.inventoryItem.update("
        new_put, m_e = patch(
            model, put_body, "put-min-integer",
            start=m_start, end=m_end,
            instr="Use !Number.isInteger(minQuantity) || in the "
                  "condition.",
            tok=90, expects=["Number.isInteger"], max_lines=4)
        if new_put:
            put_body = new_put
            meta["put_min_integer"] = m_e
        else:
            meta["put_min_integer"] = "FAILED-FOR-TEACHER"
    else:
        meta["put_min_integer"] = "covered"

    # (e) sku null literal in update data
    if "sku: sku || null" not in put_body:
        new_put, m_f = patch(
            model, put_body, "put-sku-null",
            start="data: { name, category, ",
            end=", quantity, minQuantity }",
            instr="Replace sku with sku || null.",
            tok=40, expects=["sku: sku || null"], max_lines=2)
        if new_put:
            put_body = new_put
            meta["put_sku_null"] = m_f
        else:
            meta["put_sku_null"] = "FAILED-FOR-TEACHER"
    else:
        meta["put_sku_null"] = "already-ok"

    # ---------------- POST: sku null literal ---------------------------
    post_body = cut_repetition(json.loads(
        (GEN / "route-list_post2_r1_k0.json").read_text())["processed"])
    if "sku: sku || null" not in post_body:
        new_post, m_g = patch(
            model, post_body, "post-sku-null",
            start="data: { name, category, ",
            end=", quantity, minQuantity }",
            instr="Replace sku with sku || null.",
            tok=40, expects=["sku: sku || null"], max_lines=2)
        if new_post:
            post_body = new_post
            meta["post_sku_null"] = m_g
        else:
            meta["post_sku_null"] = "FAILED-FOR-TEACHER"
    else:
        meta["post_sku_null"] = "already-ok"

    usage = dict(model.usage())
    log(f"model usage this run: {usage}")
    log("patch outcomes: " + json.dumps(meta))
    del model
    gc.collect()
    time.sleep(2)

    # ---------------- assemble + install -------------------------------
    route_list = (
        "import { NextRequest, NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "export async function GET(req: NextRequest) {\n"
        + get_body.rstrip() + "\n}\n\n"
        "export async function POST(req: NextRequest) {\n"
        + post_body.rstrip() + "\n}\n")
    p = install.APP / "src/app/api/items/route.ts"
    p.write_text(route_list)
    (GEN / "route-list_round4.ts").write_text(route_list)

    get_raw = json.loads((GEN / "body_route-id_get_r0_k1.json").read_text())
    get_id_body = cut_repetition(
        "  const { id } = await params\n" + get_raw["completion"])
    del_raw = json.loads(
        (GEN / "body_route-id_delete_r0_k1.json").read_text())
    del_body = cut_repetition(
        "  const { id } = await params\n" + del_raw["completion"])
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
    (GEN / "route-id_round4.ts").write_text(id_file)
    log("round-4 files installed + archived")

    # ---------------- gates ---------------------------------------------
    results = {}
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        results[cid] = dict(ok=ok, feedback=fb)
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:600].replace("\n", "\n  "))

    # ---------------- ledger --------------------------------------------
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    data["files"]["src/app/api/items/route.ts"] = dict(
        contract="route-list", label="QWEN-REPAIRED",
        get_body=dict(src="route-list_get3_r0_k1 + r4 patches",
                      patches={k: v for k, v in meta.items()
                               if k.startswith("get_")}),
        post_body=dict(src="route-list_post2_r1_k0 + r4 patch",
                       patches=dict(sku_null=meta.get("post_sku_null"))),
        note="round-4 surgical FIM finals; all samples archived")
    data["files"]["src/app/api/items/[id]/route.ts"] = dict(
        contract="route-id", label="QWEN-REPAIRED",
        bodies=dict(
            get=dict(src="body_route-id_get_r0_k1", cut="repetition"),
            put=dict(src="route-id_put3_r0_k0 + r4 patches",
                     patches={k: v for k, v in meta.items()
                              if k.startswith("put_")}),
            delete=dict(src="body_route-id_delete_r0_k1",
                        cut="repetition")),
        note="skeleton lines are disclosed interface scaffolding")
    data["stages"].append(dict(
        contract="route-round4", patches=meta,
        accepted=all(r["ok"] for r in results.values()),
        gates=results, usage_run=usage))
    c = data.setdefault("model_usage_cumulative", {})
    c["generations"] = c.get("generations", 0) + usage["generations"]
    c["total_new_tokens"] = (c.get("total_new_tokens", 0)
                             + usage["total_new_tokens"])
    LEDGER.write_text(json.dumps(data, indent=1))

    # ---------------- apitest --------------------------------------------
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

    log(f"round-4 complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
