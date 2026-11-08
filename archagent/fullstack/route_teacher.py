"""Route stage — TEACHER-INTEGRATION patch (Session 035).

After four model-native rounds (whole-file contracts x5 calibrations,
body contracts x3 rounds each for GET/POST/PUT, 9-region micro-FIM
ladder, imitation-FIM, literal-expression FIM; ~90 archived samples),
these specific defects were never produced correctly by the frozen
model and are now repaired by the teacher, per the frozen protocol
("record the failure, use clearly-labeled integration help only when
necessary, never fabricate success"):

  T1 GET  filters compare against a junk const (parseInt of an absent
          query param) instead of the row's a.minQuantity
  T2 PUT  quantity check block destroyed by an instruction-echo fill
          (the "landed" round-4 patch was prose, not code)
  T3 PUT  sku check rejects empty sku (spec: optional)
  T4 PUT  minQuantity check lacks Number.isInteger
  T5 PUT  bare sku in update data (spec: empty -> null)
  T6 POST bare sku in create data (spec: empty -> null)

Every edit below is counted and recorded in PROVENANCE.json under
label TEACHER-INTEGRATION with exact before/after strings.  No other
byte of the application is touched.
"""
from __future__ import annotations

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


def apply(path: Path, edits: list[tuple[str, str]], tid: str) -> list[dict]:
    text = path.read_text()
    records = []
    for old, new in edits:
        if old not in text:
            rec = dict(id=tid, error="anchor-missing",
                       anchor=old[:70])
            records.append(rec)
            log(f"  [{tid}] ANCHOR MISSING: {old[:60]!r}")
            continue
        if text.count(old) != 1:
            rec = dict(id=tid, error="anchor-not-unique",
                       anchor=old[:70])
            records.append(rec)
            log(f"  [{tid}] ANCHOR NOT UNIQUE: {old[:60]!r}")
            continue
        text = text.replace(old, new)
        rec = dict(id=tid, before=old, after=new,
                   bytes_changed=abs(len(new) - len(old)),
                   bytes_written=len(new) if old not in new else 0)
        records.append(rec)
        log(f"  [{tid}] applied: {old[:48]!r} -> {new[:48]!r} "
            f"(delta {len(new) - len(old):+d})")
    path.write_text(text)
    return records


def main() -> None:
    t0 = time.time()
    route_list = install.APP / "src/app/api/items/route.ts"
    route_id = install.APP / "src/app/api/items/[id]/route.ts"

    # archive the pre-teacher state
    (GEN / "route-list_pre_teacher.ts").write_text(route_list.read_text())
    (GEN / "route-id_pre_teacher.ts").write_text(route_id.read_text())

    all_records = []

    # T1 — GET filters use the row's minQuantity; junk const removed
    all_records += apply(route_list, [
        ("  const minQuantity = parseInt(sp.get('minQuantity') ?? '0')\n",
         ""),
        ("a.quantity > 0 && a.quantity <= minQuantity",
         "a.quantity > 0 && a.quantity <= a.minQuantity"),
        ("a.quantity > minQuantity",
         "a.quantity > a.minQuantity"),
    ], "T1-get-filters")

    # T2/T3/T4/T5 — PUT restoration
    all_records += apply(route_id, [
        # T2: echo-destroyed quantity block restored with the integer
        # check the model wrote in POST bodies (same shape it produces
        # there; the teacher restores the block the echo destroyed)
        ("""  if (quantity < 0 || quantity > 1000000) {
If you need to check if the quantity is an integer, use the !Number.isInteger() operator.
}""",
         """  if (!Number.isInteger(quantity) || quantity < 0 || quantity > 1000000) {
    return NextResponse.json({ error: 'quantity must be an integer 0-1000000' }, { status: 400 })
  }"""),
        # T3: sku optional
        ("  if (sku.length < 1 || sku.length > 40) {",
         "  if (sku.length > 40) {"),
        # T4: minQuantity integer check
        ("  if (minQuantity < 0 || minQuantity > 1000000) {",
         "  if (!Number.isInteger(minQuantity) || minQuantity < 0 "
         "|| minQuantity > 1000000) {"),
        # T5: sku null in update data
        ("data: { name, category, sku, quantity, minQuantity }",
         "data: { name, category, sku: sku || null, quantity, "
         "minQuantity }"),
    ], "T2-put-restore")

    # T6 — POST sku null in create data
    all_records += apply(route_list, [
        ("data: { name, category, sku, quantity, minQuantity }",
         "data: { name, category, sku: sku || null, quantity, "
         "minQuantity }"),
    ], "T6-post-sku-null")

    # archive post-teacher state
    (GEN / "route-list_post_teacher.ts").write_text(route_list.read_text())
    (GEN / "route-id_post_teacher.ts").write_text(route_id.read_text())

    teacher_bytes = sum(
        r.get("bytes_written", 0)
        for r in all_records if "error" not in r)
    log(f"teacher bytes written: {teacher_bytes}")

    # ---------------- gates --------------------------------------------
    results = {}
    for cid in ("route-list", "route-id"):
        contract = next(c for c in CONTRACTS if c["id"] == cid)
        ok, fb = runner_d.run_gates(contract, True)
        results[cid] = dict(ok=ok, feedback=fb)
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:600].replace("\n", "\n  "))

    # ---------------- ledger -------------------------------------------
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    data["files"]["src/app/api/items/route.ts"]["teacher"] = dict(
        label="TEACHER-INTEGRATION", edits=[
            r for r in all_records if r["id"] == "T1-get-filters"
            or r["id"] == "T6-post-sku-null"],
        teacher_bytes=teacher_bytes)
    data["files"]["src/app/api/items/[id]/route.ts"]["teacher"] = dict(
        label="TEACHER-INTEGRATION", edits=[
            r for r in all_records if r["id"] == "T2-put-restore"],
        teacher_bytes=teacher_bytes)
    data["stages"].append(dict(
        contract="route-teacher", accepted=all(
            r["ok"] for r in results.values()),
        edits=all_records, teacher_bytes=teacher_bytes,
        gates=results,
        note=("minimal disclosed integration after 4 model rounds; "
              "all model attempts archived in generations/")))
    LEDGER.write_text(json.dumps(data, indent=1))

    # ---------------- apitest -------------------------------------------
    devserver.start_dev()
    log("== apitest (frozen, as-committed; fixture bugs #7a/b still "
        "present) ==")
    try:
        r = subprocess.run(["node", str(EXP / "apitest.mjs")],
                           capture_output=True, text=True, timeout=600,
                           env=NODE_ENV, cwd=str(EXP))
        log(r.stdout)
        if r.stderr.strip():
            log("stderr: " + r.stderr[-400:])
    except subprocess.TimeoutExpired:
        log("apitest TIMEOUT")

    log(f"teacher patch complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
