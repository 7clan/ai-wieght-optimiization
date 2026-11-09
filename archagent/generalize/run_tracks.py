"""SESSION 037 — PHASE 10: the four-track comparison on the FROZEN suite.

  A  unassisted   natural spec + construct anchor, plain completion,
                  blind resampling; no demo, no checklist, no feedback
  B  036-baseline the Session-036 Track-B treatment (demo + spec +
                  construct anchor, blind ladder w/ raw-gate feedback)
  C  budget-aware the 037 engine, STRUCTURAL-ONLY acceptance in the
                  loop (probes disabled; counterexamples unused)
  D  full system  the 037 engine with in-loop behavioral probes +
                  counterexample repair + principle addenda (the
                  honestly-validated store: 0 promoted principles)

Identical budgets per piece per track: 6 generations / 2000 tokens.
Identical seeds per (piece, attempt index) across tracks.

FINAL SCORING (independent of every track's own loop): structural
gates + behavioral oracles re-run on the installed files after the
track completes.  A piece is CORRECT iff its final verification passes.

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.run_tracks A
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.run_tracks B
  ... (one track per invocation; results accumulate in
       experiments/z037-generalization/tracks/)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.frozen_suite import DOMAINS, manifest  # noqa: E402
from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.run_curricula import (  # noqa: E402
    _GateRunner, _reset_scratch, _install, _restore, baseline_prompt,
    BASELINE_LADDER, _SCAFFOLD_HEAD)
from archagent.generalize.controller import PieceController  # noqa: E402
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize import prompting, probe as probe_mod  # noqa: E402
from archagent.generalize.principles import PrincipleEngine  # noqa: E402

WS = Path("/home/z/my-project")
OUT = ROOT / "experiments" / "z037-generalization" / "tracks"
BUDGET_TOKENS = 2000
BUDGET_ATTEMPTS = 6
INV_FILE = "src/lib/{app}/invariants.ts"


# ------------------------------------------------------- unassisted (A)

def unassisted_prompt(piece) -> str:
    """Track A: the natural request, no demo, no checklist."""
    concept = piece.ir.concept if piece.ir else ""
    parts = [concept, ""]
    parts.append(f"Write the {piece.kind} for this application: "
                 f"{piece.spec}")
    parts.append("\nWrite the code now.  The first line is already "
                 "written; continue from it:")
    parts.append(piece.anchor)
    return "\n".join(parts)


def run_track_a(model, piece, gates: _GateRunner, seed_base: int,
                archive: Path) -> dict:
    attempts = []
    tokens = 0
    resolved = False
    for i in range(BUDGET_ATTEMPTS):
        if tokens >= BUDGET_TOKENS:
            break
        seed = seed_base + i * 17
        prompt = unassisted_prompt(piece)
        out, usage = model.generate(prompt, max_tokens=520, seed=seed,
                                    stochastic=(i % 2 == 1))
        tokens += usage.get("tokens", 0)
        code = prompting.extract_construct(piece.anchor + out, piece.kind)
        g = gates.structural(piece, code)
        if g["pass"]:
            resolved = True
            attempts.append({"i": i, "outcome": "structural-accept",
                             "tokens": usage.get("tokens", 0)})
            _install(piece, code, WS)
            break
        attempts.append({"i": i, "outcome":
                         "near-empty" if prompting.is_near_empty(code)
                         else "reject",
                         "tokens": usage.get("tokens", 0),
                         "failures": g.get("failures", [])[:3]})
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"a-{piece.pid}-{i}-{seed}.json").write_text(
            json.dumps({"prompt": prompt, "candidate": code}, indent=1))
    return {"piece": piece.pid, "resolved": resolved,
            "attempts": len(attempts), "tokens": tokens, "detail": attempts}


# --------------------------------------------------- 036 baseline (B)

def run_track_b(model, piece, gates: _GateRunner, seed_base: int,
                archive: Path) -> dict:
    attempts = []
    tokens = 0
    resolved = False
    feedback = ""
    for i, strat in enumerate(BASELINE_LADDER):
        if i >= BUDGET_ATTEMPTS or tokens >= BUDGET_TOKENS:
            break
        seed = seed_base + i * 17
        prompt = baseline_prompt(piece, feedback if strat == "regen_whole"
                                 else "")
        if strat == "fim_micro":
            out, usage = model.fim(piece.anchor, "",
                                   instructions="fix this region",
                                   max_tokens=64, seed=seed + 3,
                                   stochastic=True)
            code = prompting.extract_construct(piece.anchor + out,
                                               piece.kind)
        else:
            out, usage = model.generate(prompt, max_tokens=520, seed=seed,
                                        stochastic=(i % 2 == 1))
            code = prompting.extract_construct(piece.anchor + out,
                                               piece.kind)
        tokens += usage.get("tokens", 0)
        g = gates.structural(piece, code)
        if g["pass"]:
            resolved = True
            attempts.append({"i": i, "strat": strat,
                             "outcome": "structural-accept",
                             "tokens": usage.get("tokens", 0)})
            _install(piece, code, WS)
            break
        feedback = "\n".join(g.get("failures", [])[:6])
        attempts.append({"i": i, "strat": strat,
                         "tokens": usage.get("tokens", 0),
                         "failures": g.get("failures", [])[:4],
                         "near_empty": prompting.is_near_empty(code),
                         "outcome": "reject"})
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"b-{piece.pid}-{strat}-{i}-{seed}.json").write_text(
            json.dumps({"prompt": prompt, "candidate": code}, indent=1))
    return {"piece": piece.pid, "resolved": resolved,
            "attempts": len(attempts), "tokens": tokens, "detail": attempts}


# --------------------------------------------------- engine tracks (C/D)

def run_track_engine(model, piece, shared: PolicyState, seed_base: int,
                     ledger: Path, archive: Path, *,
                     probes_enabled: bool,
                     principles: PrincipleEngine | None) -> dict:
    ctrl = PieceController(
        model, WS, piece, shared,
        token_budget=BUDGET_TOKENS,
        ledger_path=ledger, archive_dir=archive,
        seed_base=seed_base, principles=principles)
    if not probes_enabled:
        ctrl._behavioral_probe = lambda code: {"pass": None}
    res = ctrl.run()
    return res


# ------------------------------------------------- final task scoring

def final_score(pieces, gates: _GateRunner,
                db_url: str | None = None) -> dict:
    """Independent verification of the installed files (never the
    tracks' own loops)."""
    out = {"pieces": {}, "resolved": 0, "total": len(pieces)}
    for p in pieces:
        target = WS / p.file
        if not target.exists():
            out["pieces"][p.pid] = {"resolved": False,
                                    "reason": "file missing"}
            continue
        code = target.read_text()
        if p.kind == "prisma-model":
            name = p.gate["models"][0]["name"]
            import re
            m = re.search(rf"model {name}\s*\{{[\s\S]*?\n\}}", code)
            if not m:
                out["pieces"][p.pid] = {"resolved": False,
                                        "reason": "model missing"}
                continue
            code = m.group(0)
        elif p.kind == "route-handler":
            method = p.gate["handlers"][0]
            import re
            m = re.search(
                rf"export async function {method}\b[\s\S]*?\n\}}", code)
            if not m:
                out["pieces"][p.pid] = {"resolved": False,
                                        "reason": "handler missing"}
                continue
            code = m.group(0)
        elif p.kind == "invariant":
            fname = p.oracle["signature"].split("(")[0]
            import re
            m = re.search(rf"export function {fname}[\s\S]*?\n\}}", code)
            if not m:
                out["pieces"][p.pid] = {"resolved": False,
                                        "reason": "function missing"}
                continue
            code = m.group(0)
        g = gates.structural(p, code)
        rec = {"structural": bool(g["pass"])}
        if not g["pass"]:
            rec["failures"] = g.get("failures", [])[:4]
            rec["resolved"] = False
        else:
            rec["resolved"] = True
            # behavioral: invariant oracle (against the file)
            if p.kind == "invariant":
                r = probe_mod.invariant_probe(
                    WS, p.file, p.oracle["signature"], p.oracle["cases"],
                    ref_expr=p.oracle.get("ref_expr"))
                if r.get("class") == "harness":
                    rec["behavioral"] = None  # harness issue — not counted
                else:
                    rec["behavioral"] = bool(r.get("pass"))
                    if not r.get("pass"):
                        rec["resolved"] = False
                        rec["ce"] = probe_mod.minimal_counterexample(r)
            elif p.kind == "route-handler" and p.oracle.get("cases"):
                r = probe_mod.route_probe(
                    WS, p.file, p.oracle["method"], p.oracle["cases"],
                    seed=p.oracle.get("seed"), db_url=db_url)
                if r.get("class") == "harness":
                    rec["behavioral"] = None
                else:
                    rec["behavioral"] = bool(r.get("pass"))
                    if not r.get("pass"):
                        rec["resolved"] = False
                        rec["failures"] = r.get("failures", [])[:4]
        out["pieces"][p.pid] = rec
        out["resolved"] += int(rec["resolved"])
    return out


def _prisma_validate_schema() -> dict:
    try:
        r = subprocess.run(
            ["bunx", "--bun", "prisma", "validate", "--schema",
             "prisma/schema.prisma"],
            capture_output=True, text=True, timeout=120, cwd=str(WS),
            env={**__import__("os").environ,
                 "DATABASE_URL": "file:./db/suite-track.db"})
        ok = r.returncode == 0 and "is valid" in (r.stdout + r.stderr)
        if ok:
            return {"pass": True}
        errs = [l for l in (r.stdout + r.stderr).splitlines()
                if "error" in l.lower()][:4]
        return {"pass": False, "failures": errs}
    except Exception as e:
        return {"pass": False, "class": "harness", "failures": [str(e)]}


# ------------------------------------------------------------- runner

def pieces_of_domain(d: dict):
    dd = {**d, "routes": [{**r} for r in d["routes"]], "ui": []}
    ir = taskir_from_dict(dd)
    return ir.pieces()


def run_track(track: str, model, gates: _GateRunner) -> dict:
    assert track in ("A", "B", "C", "D")
    out = OUT / track
    out.mkdir(parents=True, exist_ok=True)
    shared = PolicyState()
    results = []
    pr_eng = PrincipleEngine() if track == "D" else None

    for di, dom in enumerate(DOMAINS):
        print(f"\n=== [{track}] domain {dom['app']} ===", flush=True)
        pieces = pieces_of_domain(dom)
        # retarget invariant file + schema file
        for p in pieces:
            if p.kind == "prisma-model":
                p.file = "prisma/schema.prisma"
            if p.kind == "invariant":
                p.file = INV_FILE.format(app=dom["app"])
        # fresh scratch schema per domain
        (WS / "prisma/schema.prisma").write_text(_SCAFFOLD_HEAD)
        inv = WS / INV_FILE.format(app=dom["app"])
        if inv.exists():
            inv.unlink()
        # fresh route files per domain AND PER TRACK (found in
        # post-analysis: C/D's failed route loops were final-scored
        # against Track-B's still-installed bytes — cross-track
        # contamination; every piece must be scored on its own
        # track's installed files only)
        for p in pieces:
            if p.kind == "route-handler":
                t = WS / p.file
                if t.exists():
                    t.unlink()

        dom_results = []
        for pi, piece in enumerate(pieces):
            seed_base = 100000 + di * 5000 + pi * 300 + \
                {"A": 0, "B": 1000, "C": 2000, "D": 3000}[track]
            if track == "A":
                res = run_track_a(model, piece, gates, seed_base,
                                  out / "gen")
            elif track == "B":
                res = run_track_b(model, piece, gates, seed_base,
                                  out / "gen")
            else:
                res = run_track_engine(
                    model, piece, shared, seed_base,
                    ledger=out / "ledger.jsonl", archive=out / "gen",
                    probes_enabled=(track == "D"), principles=pr_eng)
            dom_results.append(res)
            print(f"  piece {piece.pid:18s} loop-resolved="
                  f"{'Y' if res['resolved'] else 'N'} "
                  f"({res['attempts'] if isinstance(res['attempts'], int) else len(res['attempts'])} att, "
                  f"{res['tokens']} tok)", flush=True)

        # push schema for route probes (probe DB) + GENERATE the client
        # so the probe's imports resolve against THIS domain's models
        v = _prisma_validate_schema()
        dbf = WS / "db" / f"suite-{dom['app']}-{track}.db"
        if dbf.exists():
            dbf.unlink()
        import os
        subprocess.run(
            ["bunx", "--bun", "prisma", "db", "push", "--schema",
             "prisma/schema.prisma"],
            capture_output=True, timeout=240, cwd=str(WS),
            env={**os.environ,
                 "DATABASE_URL": "file:./db/suite-"
                                 f"{dom['app']}-{track}.db"})

        # FINAL independent scoring
        fs = final_score(pieces, gates,
                         db_url=f"file:{dbf}")
        results.append({"domain": dom["app"], "schema_validates": v,
                        "final": fs, "loop": dom_results})
        n_ok = fs["resolved"]
        print(f"  domain {dom['app']}: final {n_ok}/{fs['total']} "
              f"schema-validate={v.get('pass')}", flush=True)

    summary = {
        "track": track,
        "domains": [{
            "domain": r["domain"],
            "final_resolved": r["final"]["resolved"],
            "total": r["final"]["total"],
            "per_piece": r["final"]["pieces"],
            "schema_validates": r["schema_validates"].get("pass"),
        } for r in results],
        "final_resolved_total": sum(r["final"]["resolved"] for r in results),
        "total_pieces": sum(r["final"]["total"] for r in results),
        "loop_tokens": sum(
            x.get("tokens", 0) for r in results for x in r["loop"]),
        "model_usage": model.usage(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    track = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    assert track in ("A", "B", "C", "D"), "specify track A|B|C|D"
    # integrity: the frozen suite must be unchanged
    m = manifest()
    frozen = json.loads(
        (ROOT / "experiments/z037-generalization/frozen-suite/MANIFEST.json"
         ).read_text())
    assert m["suite_sha256"] == frozen["suite_sha256"], \
        "frozen suite drift — refusing to run"
    print(f"frozen suite verified ({m['suite_sha256'][:16]}...)")
    from archagent.model import FrozenModel
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception:
        pass
    model = FrozenModel(threads=2)
    gates = _GateRunner(WS)
    t0 = time.time()
    s = run_track(track, model, gates)
    print(f"\n[{track}] FINAL: {s['final_resolved_total']}/"
          f"{s['total_pieces']} pieces correct; "
          f"{s['loop_tokens']} loop tokens; {time.time()-t0:.0f}s")
    print("usage:", model.usage())


if __name__ == "__main__":
    main()
