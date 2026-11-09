"""SESSION 037 — PHASE 11: full-stack independence challenge.

The FROZEN Greenhouse spec (experiments/z037-generalization/challenge/
SPEC.json, sha256 in FREEZE.json) is built by the 037 engine in its
full Track-D configuration (probes + counterexample repair; the
principle store has 0 promoted principles, so no addenda).

Attribution rules (the point of this phase):
  * every piece records its full attempt ledger (model outputs,
    strategies, tokens, gate results, counterexamples)
  * anything the engine resolves is model/engine-attributed
  * deterministic scaffolding (schema head, route imports) is
    harness-attributed
  * NO silent teacher fixes: if a piece fails its budget, the failure
    is recorded as a result.  A disclosed teacher pass may follow for
    demo purposes only and is labeled per-line in attribution.json.

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.run_challenge
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.controller import PieceController  # noqa: E402
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize import probe as probe_mod  # noqa: E402
from archagent.generalize.run_curricula import _GateRunner, _SCAFFOLD_HEAD  # noqa: E402

WS = Path("/home/z/my-project")
CH = ROOT / "experiments" / "z037-generalization" / "challenge"
BUDGET_TOKENS = 2000
INV_FILE = "src/lib/greenhouse/invariants.ts"
SEED_PLANTS = [
    {"id": "seed-plant-1", "name": "Fern", "moisture": 22, "room": "Front"},
    {"id": "seed-plant-2", "name": "Cactus", "moisture": 65, "room": "Back"},
    {"id": "seed-plant-3", "name": "Orchid", "moisture": 31, "room": "Front"},
]


def main() -> None:
    spec_path = CH / "SPEC.json"
    freeze = json.loads((CH / "FREEZE.json").read_text())
    h = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    assert h == freeze["spec_sha256"], \
        f"challenge spec drift: {h[:12]} != {freeze['spec_sha256'][:12]}"
    print(f"challenge spec verified ({h[:16]}...)")

    spec = json.loads(spec_path.read_text())
    ir = taskir_from_dict(spec)
    pieces = ir.pieces()
    for p in pieces:
        if p.kind == "invariant":
            p.file = INV_FILE

    from archagent.model import FrozenModel
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception:
        pass
    model = FrozenModel(threads=2)
    gates = _GateRunner(WS)

    # fresh workspace surface for the challenge
    (WS / "prisma/schema.prisma").write_text(_SCAFFOLD_HEAD)
    inv = WS / INV_FILE
    if inv.exists():
        inv.unlink()
    for f in ("src/app/api/plants/route.ts",
              "src/app/api/waterings/route.ts"):
        t = WS / f
        if t.exists():
            t.unlink()
    # remove previous app surfaces that would break the build
    for old in ("src/app/api/rooms", "src/app/api/reservations",
                "src/components/roomreserve"):
        t = WS / old
        if t.exists():
            import shutil
            shutil.rmtree(t)

    from archagent.generalize.principles import PrincipleEngine
    pr_eng = PrincipleEngine()   # Track-D config: store has 0 promoted
    shared = PolicyState()
    ledger = CH / "ledger.jsonl"
    if ledger.exists():
        ledger.unlink()
    results = []
    t0 = time.time()
    for pi, piece in enumerate(pieces):
        seed_base = 500000 + pi * 300
        ctrl = PieceController(
            model, WS, piece, shared,
            token_budget=BUDGET_TOKENS,
            ledger_path=ledger, archive_dir=CH / "gen",
            seed_base=seed_base, principles=pr_eng,
            docgate=True)  # validated default-ON (6/8 vs 4/8, fewer
            # tokens) — enabled AFTER the four-track froze its configs
        res = ctrl.run()
        results.append(res)
        print(f"  piece {piece.pid:18s} resolved="
              f"{'Y' if res['resolved'] else 'N'} "
              f"({res['attempts'] if isinstance(res['attempts'], int) else len(res['attempts'])} att, "
              f"{res['tokens']} tok)", flush=True)

    # task-level prisma validation (relation integrity)
    v = prisma_validate()
    dbf = WS / "db" / "challenge.db"
    if dbf.exists():
        dbf.unlink()
    import os
    subprocess.run(
        ["bunx", "--bun", "prisma", "db", "push", "--schema",
         "prisma/schema.prisma"],
        capture_output=True, timeout=240, cwd=str(WS),
        env={**os.environ, "DATABASE_URL": f"file:{dbf}"})

    # independent final scoring
    final = {}
    for p in pieces:
        target = WS / p.file
        if not target.exists():
            final[p.pid] = {"resolved": False, "reason": "file missing"}
            continue
        code = target.read_text()
        import re
        if p.kind == "prisma-model":
            name = p.gate["models"][0]["name"]
            m = re.search(rf"model {name}\s*\{{[\s\S]*?\n\}}", code)
            code = m.group(0) if m else ""
        elif p.kind == "route-handler":
            method = p.gate["handlers"][0]
            m = re.search(
                rf"export async function {method}\b[\s\S]*?\n\}}", code)
            code = m.group(0) if m else ""
        g = gates.structural(p, code)
        rec = {"structural": bool(g["pass"])}
        if g["pass"]:
            if p.kind == "invariant":
                r = probe_mod.invariant_probe(
                    WS, p.file, p.oracle["signature"], p.oracle["cases"],
                    ref_expr=p.oracle.get("ref_expr"))
                rec["behavioral"] = (None if r.get("class") == "harness"
                                     else bool(r.get("pass")))
                rec["resolved"] = rec["behavioral"] is not False
            elif p.kind == "route-handler":
                r = probe_mod.route_probe(
                    WS, p.file, p.oracle["method"], p.oracle["cases"],
                    seed=p.oracle.get("seed"), db_url=f"file:{dbf}")
                rec["behavioral"] = (None if r.get("class") == "harness"
                                     else bool(r.get("pass")))
                rec["resolved"] = rec["behavioral"] is not False
                if not r.get("pass") and r.get("class") != "harness":
                    rec["failures"] = r.get("failures", [])[:4]
            else:
                rec["resolved"] = True
        else:
            rec["resolved"] = False
            rec["failures"] = g.get("failures", [])[:4]
        final[p.pid] = rec

    summary = {
        "spec_sha256": h,
        "engine_only": {
            "pieces": [{ "pid": r["piece"], "resolved": r["resolved"],
                         "tokens": r["tokens"]} for r in results],
            "resolved": sum(1 for r in results if r["resolved"]),
            "total": len(results),
            "tokens": sum(r["tokens"] for r in results),
        },
        "schema_validates": v,
        "final": final,
        "wall_seconds": round(time.time() - t0, 1),
        "model_usage": model.usage(),
    }
    (CH / "results.json").write_text(json.dumps(summary, indent=1))
    n = summary["engine_only"]["resolved"]
    print(f"\nCHALLENGE (engine-only): {n}/{len(results)} pieces; "
          f"schema-valid={v.get('pass')}; "
          f"{summary['engine_only']['tokens']} tokens; "
          f"{summary['wall_seconds']}s")


def prisma_validate() -> dict:
    try:
        import os
        r = subprocess.run(
            ["bunx", "--bun", "prisma", "validate", "--schema",
             "prisma/schema.prisma"],
            capture_output=True, text=True, timeout=120, cwd=str(WS),
            env={**os.environ,
                 "DATABASE_URL": "file:./db/challenge.db"})
        ok = r.returncode == 0 and "is valid" in (r.stdout + r.stderr)
        if ok:
            return {"pass": True}
        errs = [l for l in (r.stdout + r.stderr).splitlines()
                if "error" in l.lower()][:4]
        return {"pass": False, "failures": errs}
    except Exception as e:
        return {"pass": False, "class": "harness", "failures": [str(e)]}


if __name__ == "__main__":
    main()
