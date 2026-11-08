"""SESSION 036 — RoomReserve Tracks B and C (staged, zero teacher).

Track B — fixed-strategy baseline (Session-035 approach, corrected
gates): per contract, an 8-generation budget walked through a FIXED
ladder [exact_shape x4, regen_whole(feedback) x2, fim_micro x2].

Track C — adaptive self-repair: same contracts, same 8-generation
budget, same structural gates; the Thompson-sampling bandit chooses the
strategy ORDER (armed with Session-035-mined priors), doc_lookup may
consult the frozen docs bundle, and every attempt is ledgered with
diagnosis/strategy/why/result/policy-update.

Both tracks: NO teacher bytes, NO L2 named fixes, NO harness-inserted
code.  Model loaded once; dev server stopped (RAM discipline).
Structural gates run per attempt; tsc + frozen dynamic suites run at
assembly time (model unloaded).

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.fullstack.rr_track_bc B
  ARCHAGENT_MODEL_DIR=... python -m archagent.fullstack.rr_track_bc C
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver  # noqa: E402
from archagent.fullstack.rr_contracts import (  # noqa: E402
    ALL_CONTRACTS, CONCEPT)
from archagent.repair.controller import RepairController  # noqa: E402

EXP = ROOT / "experiments" / "z036-roomreserve"
GEN = EXP / "generations"
REPORTS = EXP / "reports"
WS = Path("/home/z/my-project")
DOCS_BUNDLE = EXP / "docs-bundle"

BUDGET_PER_CONTRACT = 8
TRACK_B_LADDER = ["exact_shape", "exact_shape", "regen_whole", "fim_micro"]


def load_docs() -> str:
    parts = []
    for name in ("nextjs-route-handlers.txt", "prisma-client-api.txt"):
        p = DOCS_BUNDLE / name
        if p.exists():
            parts.append(p.read_text()[:2600])
    return "\n\n".join(parts)


def contract_defect(contract: dict, current_code: str) -> dict:
    """Turn a generation contract into a controller defect.

    gate_failures: the contract's own expectations phrased as the
    diagnosis (what a passing file must contain).  The controller's
    structural gate then verifies the candidate against `expect`.
    """
    expect = contract["expect"]
    fails = []
    for h in expect.get("handlers", []):
        fails.append(f"exports: HTTP handler '{h}' not exported")
    for c in expect.get("calls", []):
        fails.append(f"calls: '{c}' not found as a reachable call "
                     "expression")
    for c in expect.get("accesses", []):
        fails.append(f"accesses: '{c}' not found in reachable code")
    if expect.get("uiStrings"):
        fails.append("uiStrings: required strings not in used positions")
    return {
        "file": contract["file"],
        "code": current_code,
        "contract": {
            **expect,
            "file": contract["file"],
            "demo": contract.get("demo", ""),
            "spec": contract["spec"],
            "anchor": contract.get("anchor"),
            "max_tokens": contract.get("max_tokens", 700),
            "instruction": contract["spec"],
        },
        "gate_failures": fails,
        "diagnosis": None,  # generation, not repair: the spec IS the task
        "region": {},
        "concept": CONCEPT,
    }


def seed_gate_for(contract: dict) -> dict:
    """Structural contract used to verify candidates (the expect block)."""
    e = dict(contract["expect"])
    e["file"] = contract["file"]
    e["instruction"] = contract["spec"]
    e["demo"] = contract.get("demo", "")
    e["spec"] = contract["spec"]
    e["anchor"] = contract.get("anchor")
    e["max_tokens"] = contract.get("max_tokens", 700)
    return e


def install_file(path: str, code: str) -> None:
    dest = WS / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(code)


SCAFFOLD_SCHEMA = """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model Post {
  id        String   @id @default(cuid())
  title     String
  content   String?
  published Boolean  @default(false)
  authorId  String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
"""


def merge_schema(model_block: str) -> None:
    """Deterministic scaffold merge: canonical head + candidate models."""
    (WS / "prisma/schema.prisma").write_text(
        SCAFFOLD_SCHEMA + "\n" + model_block + "\n")


def main() -> None:
    track = (sys.argv[1] if len(sys.argv) > 1 else "B").upper()
    assert track in ("B", "C")
    from archagent.model import FrozenModel
    from archagent.repair.bandit import StrategyBandit

    devserver.stop_dev()
    model = FrozenModel(threads=2)
    docs = load_docs()
    priors = json.loads(
        (ROOT / "experiments" / "z036" / "prior-mining.json").read_text()
    )["priors"]

    ledger = EXP / f"track{track}-ledger.jsonl"
    state = EXP / f"track{track}-bandit.json"
    ctrl = RepairController(
        model, str(WS), str(ledger), state_path=str(state),
        priors=priors if track == "C" else None,
        budget_per_defect=BUDGET_PER_CONTRACT,
        fixed_ladder=(track == "B"),
        ladder=TRACK_B_LADDER,
        bandit_seed=(11 if track == "B" else 23),
        archive_dir=str(EXP / "generations" / f"track{track}"))

    results = []
    t_start = time.time()
    for contract in ALL_CONTRACTS:
        # current workspace state of the target file (may not exist)
        cur = (WS / contract["file"])
        current = cur.read_text() if cur.exists() else ""
        defect = contract_defect(contract, current)
        defect["contract"] = seed_gate_for(contract)

        res = ctrl.repair(defect, docs=docs,
                          seed_base=3000 + 111 * len(results))
        # keep the resolved file ONLY if it exists on disk (controller
        # installs on success); otherwise record failure and continue
        entry = {
            "contract": contract["key"], "file": contract["file"],
            "category": res["category"],
            "resolved": res["resolved"],
            "resolved_by": res.get("resolved_by"),
            "provenance": res.get("provenance"),
            "attempts": len(res["attempts"]),
            "tokens": res["tokens"],
            "strategy_order": res["strategy_order"],
            "seconds": res["seconds"],
        }
        results.append(entry)
        print(f"  [{track}] {contract['key']:22s} "
              f"{'RESOLVED by ' + str(res.get('resolved_by')) if res['resolved'] else 'FAILED'} "
              f"({len(res['attempts'])} attempts, {res['tokens']} tok)")
        if contract["kind"] == "prisma":
            if res["resolved"]:
                # the controller installed the raw model blocks; merge
                # into the canonical scaffold deterministically
                raw = (WS / "prisma/schema.prisma").read_text()
                merge_schema(raw)
                subprocess.run(["bun", "run", "db:push"], cwd=str(WS),
                               capture_output=True, timeout=240)
            else:
                # no Room/Reservation models -> later route gates would
                # all fail; restore scaffold so the failure is isolated
                merge_schema("")

    summary = ctrl.summary()
    report = {
        "track": track, "mode": "fixed-ladder" if track == "B" else "adaptive",
        "budget_per_contract": BUDGET_PER_CONTRACT,
        "contracts": results,
        "resolved": sum(1 for r in results if r["resolved"]),
        "total": len(results),
        "generations": sum(r["attempts"] for r in results),
        "tokens": sum(r["tokens"] for r in results),
        "wall_seconds": round(time.time() - t_start, 1),
        "model_usage": model.usage(),
        "bandit_snapshot": summary.get("bandit"),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"track{track}.json").write_text(json.dumps(report, indent=1))
    print(f"\n[{track}] {report['resolved']}/{report['total']} contracts "
          f"resolved, {report['generations']} generations, "
          f"{report['tokens']} tokens, {report['wall_seconds']}s")
    print("report ->", REPORTS / f"track{track}.json")


if __name__ == "__main__":
    main()
