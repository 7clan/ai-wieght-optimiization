"""SESSION 037 — Phase 2 smoke test: the full TaskIR path on a miniature
application (a delivery-windows scheduler — NOT any benchmark domain).

Validates, with REAL frozen-model inference:
  1. taskir_from_dict validation (relation integrity, case tables)
  2. pieces() topological decomposition
  3. prompt construction laws (anchor-inside, demo-completeness)
  4. the policy state machine (incl. early-EOS retry, micro-repair)
  5. structural gates incl. the new invariant kind
  6. behavioral probes (case table + fuzz vs reference oracle)
  7. file assembly + provenance labeling

Run:  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.smoke
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.controller import PieceController  # noqa: E402
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize import prompting  # noqa: E402

WS = Path("/home/z/my-project")
OUT = ROOT / "experiments" / "z037-generalization" / "phase2-smoke"

MINI_IR = {
    "app": "courier",
    "concept": ("CourierWin: a courier delivery-window scheduler. "
                "Deliveries are parcels with a pickup window and a dropoff "
                "window; a courier cannot have two dropoffs whose windows "
                "overlap."),
    "entities": [
        {"pid": "courier-parcel", "name": "Parcel",
         "fields": [
             {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
             {"name": "code", "type": "String"},
             {"name": "courierId", "type": "String"},
             {"name": "dropStart", "type": "String"},
             {"name": "dropEnd", "type": "String"}],
         "relations": [
             {"name": "courier", "target": "Courier", "kind": "many-to-one",
              "is_list": False, "fk_field": "courierId"}],
         "demo_domain": (
             "model VetVisit {\n"
             "  id        String  @id @default(cuid())\n"
             "  petName   String\n"
             "  vetId     String\n"
             "  visitStart String\n"
             "  visitEnd   String\n"
             "  vet       Vet     @relation(fields: [vetId], references: [id])\n"
             "}\n\n"
             "model Vet {\n"
             "  id        String  @id @default(cuid())\n"
             "  name      String\n"
             "  visits    VetVisit[]\n"
             "}")},
        {"pid": "courier-driver", "name": "Courier",
         "fields": [
             {"name": "id", "type": "String", "attrs": ["@id", "@default(cuid())"]},
             {"name": "name", "type": "String"}],
         "relations": [
             {"name": "parcels", "target": "Parcel", "kind": "one-to-many",
              "is_list": True}],
         "demo_domain": (
             "model Vet {\n"
             "  id        String  @id @default(cuid())\n"
             "  name      String\n"
             "  visits    VetVisit[]\n"
             "}")},
    ],
    "invariants": [
        {"pid": "courier-no-overlap", "statement":
         ("windowsOverlap is true exactly when one window starts strictly "
          "before the other ends AND the other starts strictly before the "
          "first ends (touching endpoints do NOT overlap)."),
         "signature": "windowsOverlap(aStart: string, aEnd: string, bStart: string, bEnd: string)",
         "cases": [
             {"name": "disjoint", "inputs": ["2026-01-01T09:00", "2026-01-01T10:00", "2026-01-01T11:00", "2026-01-01T12:00"], "expect": False},
             {"name": "touching", "inputs": ["2026-01-01T09:00", "2026-01-01T10:00", "2026-01-01T10:00", "2026-01-01T11:00"], "expect": False},
             {"name": "partial", "inputs": ["2026-01-01T09:00", "2026-01-01T11:00", "2026-01-01T10:00", "2026-01-01T12:00"], "expect": True},
             {"name": "nested", "inputs": ["2026-01-01T09:00", "2026-01-01T13:00", "2026-01-01T10:00", "2026-01-01T11:00"], "expect": True},
             {"name": "identical", "inputs": ["2026-01-01T09:00", "2026-01-01T10:00", "2026-01-01T09:00", "2026-01-01T10:00"], "expect": True}],
         "ref_expr": "aStart < bEnd && bStart < aEnd",
         "demo_domain": (
             "// gym class double-booking check (different domain)\n"
             "export function slotsClash(aFrom: string, aTo: string,\n"
             "                            bFrom: string, bTo: string) {\n"
             "  return aFrom < bTo && bFrom < aTo\n"
             "}\n")},
    ],
    "routes": [],
    "ui": [],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ir = taskir_from_dict(MINI_IR)
    pieces = ir.pieces()
    print(f"[smoke] TaskIR valid; {len(pieces)} pieces:")
    for p in pieces:
        errs = prompting.validate_demo(p)
        print(f"  - {p.pid:22s} kind={p.kind:14s} file={p.file} "
              f"deps={p.depends_on} demo_ok={'YES' if not errs else errs}")

    # ---- real inference on the invariant piece (the centerpiece) ----
    from archagent.model import FrozenModel
    devserver_stop()
    model = FrozenModel(threads=2)
    state = PolicyState()
    inv = [p for p in pieces if p.kind == "invariant"][0]

    ledger = OUT / "smoke-ledger.jsonl"
    if ledger.exists():
        ledger.unlink()
    ctrl = PieceController(
        model, WS, inv, state,
        token_budget=2400,
        ledger_path=ledger,
        archive_dir=OUT / "generations",
        seed_base=9000)
    result = ctrl.run()
    print(f"\n[smoke] invariant piece: resolved={result['resolved']} "
          f"attempts={len(result['attempts'])} tokens={result['tokens']}")
    for a in result["attempts"]:
        print(f"   step {a.get('step')}: {a.get('action'):22s} "
              f"outcome={str(a.get('outcome'))[:70]}")
        if a.get("probe"):
            print(f"      probe pass={a['probe']['pass']} "
                  f"ce={a['probe'].get('counterexample','')[:90]}")
    print("\n[smoke] usage:", model.usage())
    (OUT / "smoke-result.json").write_text(json.dumps(result, indent=1))
    print("[smoke] artifacts ->", OUT)


def devserver_stop() -> None:
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception as e:
        print("[smoke] devserver stop skipped:", e)


if __name__ == "__main__":
    main()
