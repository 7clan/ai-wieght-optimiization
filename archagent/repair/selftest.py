"""SESSION 036 — PHASE 2/3 SELF-TEST (TRUSTED-SCAFFOLD).

End-to-end validation of the adaptive repair controller with REAL
frozen-model inference on REAL defects:

  1. take the archived (verified) StockPilot route file,
  2. inject a known defect (surgical removal of one expression),
  3. run the controller within a small budget,
  4. check whether the frozen model repairs it — provenance always L1.

Defects (one per salient category):
  D1 missing_literal : remove `sku: sku || null` from POST (the
                       documented 15/15 one-literal miss of Session 035)
  D2 missing_call    : remove the Number.isInteger validation call
  D3 wrong_contract  : break the low-stock filter (bare minQuantity)

This is a CONTROLLER test, not a RoomReserve scored run; results feed
the ablation design.  The dev server is stopped during generation
(Session-035 RAM discipline) and restarted for probes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from archagent.model import FrozenModel  # noqa: E402
from archagent.repair.controller import RepairController  # noqa: E402
from archagent.repair import strategies as S  # noqa: E402

WS = Path("/home/z/my-project")
OUT = REPO / "experiments" / "z036"
ROUTE = "src/app/api/items/route.ts"

CONCEPT = ("You are writing a Next.js 16 inventory app (StockPilot). "
           "TypeScript, Prisma+SQLite, NextResponse JSON APIs.")

CONTRACT = {
    "kind": "route",
    "file": ROUTE,
    "handlers": ["GET", "POST"],
    "calls": ["NextResponse.json", "Number.isInteger"],
    "accesses": ["db.inventoryItem"],
    "exprs": ["a.quantity<=a.minQuantity"],
    "instruction": ("Write the inventory items route: GET lists items with "
                    "search, category, status filters and sorting; POST "
                    "validates name, category, quantity, minQuantity "
                    "integers and optional sku."),
}


def stop_dev():
    subprocess.run(["pkill", "-f", "next dev"], capture_output=True)
    subprocess.run(["pkill", "-f", "next-server"], capture_output=True)
    time.sleep(2)


def inject(code: str, which: str) -> tuple[str, str]:
    """Surgically remove one known-good region; return (broken, region)."""
    if which == "D1":
        # remove the sku null-coalescing literal from POST create data
        needle = "sku: sku || null"
        assert needle in code, "D1 needle missing"
        idx = code.index(needle)
        # region context for micro strategies
        pre_end = code.rindex("\n", 0, idx) + 1
        prefix = code[:pre_end]
        suffix = code[idx + len(needle):]
        broken = code.replace(needle, "sku: sku", 1)
        return broken, {"prefix": prefix, "suffix": suffix}
    if which == "D2":
        # remove the Number.isInteger validation call (whole condition)
        lines = code.split("\n")
        out, hit = [], False
        for ln in lines:
            if not hit and "Number.isInteger" in ln and "quantity" in ln:
                hit = True
                continue  # drop the condition line
            out.append(ln)
        assert hit, "D2 needle missing"
        return "\n".join(out), {}
    if which == "D3":
        # break the low-stock filter semantics
        needle = "a.quantity > 0 && a.quantity <= a.minQuantity"
        assert needle in code, "D3 needle missing"
        idx = code.index(needle)
        pre_end = code.rindex("\n", 0, idx) + 1
        region = {"prefix": code[:pre_end], "suffix": code[idx + len(needle):]}
        broken = code.replace(needle, "a.minQuantity", 1)
        return broken, region
    raise ValueError(which)


# SEMANTIC diagnoses: teacher states the REQUIREMENT without writing the
# code.  The model must choose the fix (L1 provenance if it succeeds).
DIAGNOSES = {
    "D1": "create data must store null for an absent optional sku",
    "D2": "quantity and minQuantity must be rejected when not integers",
    "D3": "low-stock means quantity above zero and at or below the minimum",
}


def expected_gate_failures(which: str) -> list[str]:
    if which == "D1":
        # the one-literal gap is NOT visible to AST gates (sku: sku is
        # valid code) — it is a dynamic/contract-level failure; we model
        # it as a contract expectation via a body-level literal check
        return ["missing 'sku: sku || null'"]
    if which == "D2":
        return ["calls: 'Number.isInteger' not found as a reachable call "
                "expression (comments/strings/unreachable code never "
                "satisfy this gate)"]
    if which == "D3":
        return ["forbidden bare 'a.minQuantity' filter (low-stock must be "
                "a.quantity > 0 && a.quantity <= a.minQuantity)"]
    return []


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    original = (WS / ROUTE).read_text()

    # richer contract for D1: literal expectation enforced via a
    # contract-level expects list (the controller feeds it to strategies
    # as the diagnosis)
    d1_contract = {**CONTRACT,
                   "spec": CONTRACT["instruction"] + " POST must store "
                   "sku as null when absent (sku: sku || null).",
                   "body_spec": "POST body: parse json; validate; create "
                   "with sku: sku || null."}

    defects = []
    for which, contract in (("D1", d1_contract), ("D2", CONTRACT),
                            ("D3", CONTRACT)):
        broken, region = inject(original, which)
        defects.append({
            "which": which, "file": ROUTE, "code": broken,
            "contract": {**contract,
                         "instruction": contract["instruction"]},
            "gate_failures": expected_gate_failures(which),
            "diagnosis": DIAGNOSES[which],
            "region": region, "concept": CONCEPT,
        })

    print("== controller self-test: real inference, 3 injected defects ==")
    stop_dev()
    model = FrozenModel(threads=2)
    print(f"model loaded, usage so far: {model.usage()}")

    results = []
    for d in defects:
        ctrl = RepairController(
            model, str(WS), str(OUT / "selftest-ledger.jsonl"),
            state_path=str(OUT / "selftest-bandit.json"),
            budget_per_defect=6, fixed_ladder=False, bandit_seed=7)
        # D1's literal gap needs a gate that can see it: use a targeted
        # probe-style contract — wrap structural gate with literal check
        if d["which"] == "D1":
            d["contract"] = {**d["contract"], "calls": ["NextResponse.json"]}
        res = ctrl.repair(d)
        results.append({"which": d["which"], **{
            k: v for k, v in res.items() if k != "attempts"},
            "attempt_summaries": [
                {"strategy": a.get("strategy"),
                 "outcome": str(a.get("outcome"))[:120]}
                for a in res["attempts"]]})
        print(f"  {d['which']}: resolved={res['resolved']} "
              f"by={res['resolved_by']} category={res['category']} "
              f"attempts={len(res['attempts'])} tokens={res['tokens']}")

    # restore the pristine file regardless of outcome
    (WS / ROUTE).write_text(original)

    # final verification that the archive is intact
    gate = RepairController(model, str(WS), "/tmp/x.jsonl")
    verdict = gate.structural_gate(original, CONTRACT)
    print(f"pristine file re-verified after restore: {verdict['pass']}")

    report = {
        "model_usage": model.usage(),
        "results": results,
        "note": "controller self-test on injected defects; provenance of "
                "any successful patch is L1 (Qwen-chosen from diagnosis)",
    }
    (OUT / "selftest-report.json").write_text(json.dumps(report, indent=1))
    print(f"model usage total: {model.usage()}")
    print("report -> experiments/z036/selftest-report.json")


if __name__ == "__main__":
    main()
