"""SESSION 037 — PHASE 4 VALIDATION: principle promotion A/B.

Validation pieces: curriculum tasks the ENGINE failed (held back from
further tuning): A.4 rel-two (Order piece), B.2 inv-exclusive, B.4
inv-window.  For each candidate principle whose trigger matches, run
the piece WITH the addendum and WITHOUT (identical seeds, budgets,
policy) and record the pair as promotion evidence.

Usage: ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.validate_principles
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.curricula import (  # noqa: E402
    CURRICULUM_A, CURRICULUM_B, WS, OUT)
from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.run_curricula import (  # noqa: E402
    _retarget_schema_pieces, _GateRunner, _reset_scratch, _install,
    _restore, run_engine)
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize.principles import (  # noqa: E402
    PrincipleEngine, Evidence)

VAL_OUT = OUT / "principle-validation"


def _pieces_for(task: dict, which: str):
    if which == "A":
        d = {"app": "curriculumA", "concept": "A small relational store.",
             "entities": [{**e, "demo_domain": task["demo"]}
                          for e in task["entities"]],
             "invariants": [], "routes": [], "ui": []}
        return _retarget_schema_pieces(taskir_from_dict(d).pieces())
    d = {"app": "curriculumB", "concept": "A small logic library.",
         "entities": [], "routes": [], "ui": [],
         "invariants": [{k: v for k, v in task.items()
                         if k in ("pid", "statement", "signature",
                                  "cases", "demo_domain", "ref_expr")}]}
    return taskir_from_dict(d).pieces()


def main() -> None:
    from archagent.model import FrozenModel
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception:
        pass
    model = FrozenModel(threads=2)
    gates = _GateRunner(WS)
    eng = PrincipleEngine()
    VAL_OUT.mkdir(parents=True, exist_ok=True)

    # validation pieces: engine-failed curriculum tasks
    val_tasks = [
        ("A", [t for t in CURRICULUM_A if t["pid"] == "rel-two"][0]),
        ("B", [t for t in CURRICULUM_B if t["pid"] == "inv-exclusive"][0]),
        ("B", [t for t in CURRICULUM_B if t["pid"] == "inv-window"][0]),
    ]

    # principles to validate: all candidates
    cands = [p for p in eng.principles if p.status == "candidate"]
    print(f"validating {len(cands)} candidate principles on "
          f"{len(val_tasks)} held-back failure tasks\n")

    ledger = VAL_OUT / "ledger.jsonl"
    for which, task in val_tasks:
        pieces = _pieces_for(task, which)
        # pick the piece matching the principle trigger kind
        for p in cands:
            matching = [pc for pc in pieces if pc.kind == p.trigger_kind]
            if not matching:
                continue
            piece = matching[0]
            for condition in ("without", "with"):
                _reset_scratch(WS)
                # fresh state per condition (no cross-contamination)
                pr_eng = PrincipleEngine() if condition == "with" else None
                if condition == "with":
                    # force THIS principle active for validation
                    for q in pr_eng.principles:
                        if q.pid == p.pid:
                            q.status = "validating"
                shared = PolicyState()
                res = run_engine(
                    model, piece, shared,
                    seed_base=80000 + hash(piece.pid) % 1000,
                    ledger=ledger, archive=VAL_OUT / f"{condition}-gen",
                    principles=pr_eng)
                outcome = "resolved" if res["resolved"] else "failed"
                rec = {"principle": p.pid, "piece": piece.pid,
                       "task": task["pid"], "condition": condition,
                       "resolved": res["resolved"],
                       "tokens": res["tokens"],
                       "attempts": len(res["attempts"])}
                with open(ledger, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
                print(f"  {p.pid} x {piece.pid:24s} {condition:8s} "
                      f"-> {'RESOLVED' if res['resolved'] else 'failed  '}"
                      f" ({len(res['attempts'])} att, {res['tokens']} tok)")
                ev = Evidence(task=piece.pid, piece_kind=piece.kind,
                              without="", with_="")
                # evidence recorded per pair below
    print("\nusage:", model.usage())


if __name__ == "__main__":
    main()
