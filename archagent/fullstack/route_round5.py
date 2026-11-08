"""Route stage, round 5 — type-level FIM finals (Session 035).

The teacher restoration unmasked two type-level defects in the GET
body (runtime-correct, tsc-failing; SWC does not typecheck, which is
why apitest passed 9/16 with them present):

  U1  the where const's annotation lacks `category?: string`
  U2  `order` is `string` where Prisma's orderBy needs 'asc' | 'desc'

Both are single-line, literal-shaped edits — one last model round in
the format that has landed such edits before (adjacent, literal
instruction, tiny gap).  Failures go to the teacher, disclosed.
"""
from __future__ import annotations

import gc
import json
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
from archagent.fullstack.route_round2 import _balance  # noqa: E402
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
          tok: int, expects: list[str], max_lines: int = 3
          ) -> tuple[str | None, dict]:
    i = base.find(start)
    j = base.find(end, i + len(start)) if end else len(base)
    if i == -1 or j == -1:
        log(f"  [{pid}] anchors missing")
        return None, dict(error="anchors-missing")
    prefix, suffix = base[:i + len(start)], base[j:]
    for k in range(3):
        seed = k * 1013 or 7
        text, usage = model.fim(prefix=prefix, suffix=suffix,
                                instructions=instr, max_tokens=tok,
                                seed=seed, stochastic=k != 0)
        fill = text.strip("\n")
        reasons = []
        for w in DEMO_ECHO:
            if w in fill:
                reasons.append(f"demo echo {w!r}")
        for need in expects:
            if need not in fill:
                reasons.append(f"missing {need!r}")
        if len(fill.splitlines()) > max_lines:
            reasons.append("too long")
        if not fill.strip():
            reasons.append("empty")
        cand = prefix + fill + ("\n" if fill and not fill.endswith("\n")
                                else "") + suffix
        if reasons == [] and not _balance(cand):
            reasons.append("imbalance")
        ok = not reasons
        (GEN / f"r5_{pid}_k{k}.json").write_text(json.dumps(
            dict(kind="fim-patch", pid=pid, k=k, seed=seed, usage=usage,
                 instructions=instr, completion=text,
                 reject=reasons or None), ensure_ascii=False, indent=1))
        log(f"  [r5 {pid} k{k}] seed={seed} tok={usage['tokens']} "
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

    route_list = install.APP / "src/app/api/items/route.ts"
    base = route_list.read_text()
    meta: dict = {}

    # U1 — where annotation gains category?: string
    new_base, m = patch(
        model, base, "where-type-category",
        start="  const where: { OR?: { name: { contains: string } }[]",
        end=" = {}\n",
        instr="Add category?: string to the type.",
        tok=60, expects=["category?: string"], max_lines=2)
    if new_base:
        base = new_base
        meta["where_type_category"] = m
    else:
        meta["where_type_category"] = "FAILED-FOR-TEACHER"

    # U2 — order typed as 'asc' | 'desc'
    new_base, m = patch(
        model, base, "order-type",
        start="  const order = sp.get('order') ?? 'desc'\n",
        end="",
        instr="Cast the value so order is 'asc' or 'desc'.",
        tok=60, expects=["'asc' | 'desc'"], max_lines=1)
    if new_base:
        base = new_base
        meta["order_type"] = m
    else:
        meta["order_type"] = "FAILED-FOR-TEACHER"

    usage = dict(model.usage())
    log(f"model usage this run: {usage}")
    log("r5 outcomes: " + json.dumps(meta))
    del model
    gc.collect()
    time.sleep(2)

    # teacher fallback for the failures (same disclosure discipline)
    teacher_edits = []
    if meta["where_type_category"] == "FAILED-FOR-TEACHER":
        old = ("  const where: { OR?: { name: { contains: string } }[] }"
               " = {}")
        new = ("  const where: { OR?: { name: { contains: string } }[]; "
               "category?: string } = {}")
        if old in base:
            base = base.replace(old, new)
            teacher_edits.append(dict(id="U1", before=old, after=new))
            log("  [U1 teacher] applied")
    if meta["order_type"] == "FAILED-FOR-TEACHER":
        old = "  const order = sp.get('order') ?? 'desc'"
        new = ("  const order = (sp.get('order') ?? 'desc') as "
               "'asc' | 'desc'")
        if old in base:
            base = base.replace(old, new)
            teacher_edits.append(dict(id="U2", before=old, after=new))
            log("  [U2 teacher] applied")

    route_list.write_text(base)
    (GEN / "route-list_round5.ts").write_text(base)

    results = {}
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        results[cid] = dict(ok=ok, feedback=fb)
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:500].replace("\n", "\n  "))

    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    rec = data["files"].get("src/app/api/items/route.ts", {})
    rec["round5"] = dict(patches=meta, teacher=teacher_edits,
                         note="type-level finals; U1/U2")
    data["stages"].append(dict(
        contract="route-round5", patches=meta,
        teacher_edits=teacher_edits,
        accepted=all(r["ok"] for r in results.values()),
        gates=results, usage_run=usage))
    c = data.setdefault("model_usage_cumulative", {})
    c["generations"] = c.get("generations", 0) + usage["generations"]
    c["total_new_tokens"] = (c.get("total_new_tokens", 0)
                             + usage["total_new_tokens"])
    LEDGER.write_text(json.dumps(data, indent=1))

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
    log(f"round-5 complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
