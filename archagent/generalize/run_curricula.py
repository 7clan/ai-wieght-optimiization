"""SESSION 037 — PHASE 7 RUNNER: baseline vs engine on both curricula.

Baseline = the Session-036 Track-B treatment (its documented prompt
format, its [exact_shape x4, regen(feedback) x2, fim_micro x2] ladder,
no domain-diff line, no counterexample usage, no forced continuation,
blind budget burn).  Engine = the TaskIR piece treatment.  Both verify
with the SAME structural gates + behavioral oracles (case tables, fuzz,
prisma validate).  Identical budgets: 6 generations / 2000 tokens.

Schema pieces run against a SCRATCH schema file (never the workspace
app schema); validation uses `prisma validate` (no client generation,
no DB writes).

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.run_curricula A
  ARCHAGENT_MODEL_DIR=... python -m archagent.generalize.run_curricula B
"""
from __future__ import annotations

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
from archagent.generalize import prompting  # noqa: E402
from archagent.generalize import probe as probe_mod  # noqa: E402
from archagent.generalize.curricula import (  # noqa: E402
    CURRICULUM_A, CURRICULUM_B, WS, OUT, BUDGET_TOKENS, BUDGET_ATTEMPTS)

SCHEMA_FILE = "prisma/curriculum-schema.prisma"
INV_FILE = "src/lib/curriculum/invariants.ts"
BASELINE_LADDER = (["exact_shape"] * 4 + ["regen_whole"] * 2
                   + ["fim_micro"] * 2)


# ------------------------------------------------------------- helpers

def _piece_of(ir_pieces, pid):
    for p in ir_pieces:
        if p.pid == pid:
            return p
    raise KeyError(pid)


def _retarget_schema_pieces(pieces):
    for p in pieces:
        if p.kind == "prisma-model":
            p.file = SCHEMA_FILE
    return pieces


def _prisma_validate(ws: Path) -> dict:
    """Behavioral schema probe: prisma's own validator (relation arity,
    optionality matching, named-relation rules)."""
    try:
        r = subprocess.run(
            ["bunx", "--bun", "prisma", "validate", "--schema",
             SCHEMA_FILE],
            capture_output=True, text=True, timeout=120, cwd=str(ws),
            env={**__import__("os").environ,
                 "DATABASE_URL": "file:./db/curriculum.db"})
        ok = r.returncode == 0 and "is valid" in (r.stdout + r.stderr)
        if ok:
            return {"pass": True}
        msg = (r.stdout + r.stderr)
        errs = [l for l in msg.splitlines()
                if "error" in l.lower() or "Error" in l][:4]
        return {"pass": False, "class": "app", "failures": errs}
    except Exception as e:
        return {"pass": False, "class": "harness",
                "failures": [f"prisma validate crashed: {e}"]}


def _reset_scratch(ws: Path) -> None:
    (ws / SCHEMA_FILE).parent.mkdir(parents=True, exist_ok=True)
    (ws / SCHEMA_FILE).write_text(_SCAFFOLD_HEAD)
    inv = ws / INV_FILE
    if inv.exists():
        inv.unlink()


_SCAFFOLD_HEAD = """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}
"""


# ------------------------------------------------------- baseline loop

def baseline_prompt(piece, feedback: str = "") -> str:
    """The EXACT Session-036 Track-B prompt format (documented in
    archagent/repair/strategies.py s_exact_shape / s_regen_whole)."""
    concept = piece.ir.concept if piece.ir else ""
    parts = [concept, "", piece.demo, ""]
    parts.append(f"Now YOUR task.  Write the file {piece.file} for the "
                 "application.")
    parts.append(piece.spec)
    if feedback:
        parts.append("\nThe automated checks reported:")
        parts.append("\n".join(feedback.splitlines()[:6]))
        parts.append("Fix exactly that.")
    parts.append("\nWrite the complete file now.  The first line is "
                 "already written; continue from it:")
    parts.append(piece.anchor)
    return "\n".join(parts)


class _GateRunner:
    """Shared verification for both treatments."""

    def __init__(self, ws: Path):
        self.ws = ws

    def structural(self, piece, code: str) -> dict:
        import os
        from archagent.generalize.controller import VERIFY, NODE_ENV_PATH
        contract = dict(piece.gate)
        contract["file"] = piece.file
        if contract.get("kind") == "invariant":
            contract["function"] = piece.oracle["signature"].split("(")[0]
        cf = self.ws / ".z037-contract.json"
        cf.write_text(json.dumps(contract))
        try:
            r = subprocess.run(
                ["node", str(VERIFY), "--contract", str(cf), "--stdin"],
                input=code, capture_output=True, text=True, timeout=90,
                cwd=str(self.ws),
                env={**os.environ, "NODE_PATH": NODE_ENV_PATH})
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:
            return {"pass": False, "failures": [f"harness error: {e}"]}

    def behavioral(self, piece, code: str) -> tuple[bool | None, str]:
        """Returns (pass|None, counterexample).  None = harness issue.

        prisma-model pieces have NO piece-level behavioral probe: a
        relation cannot validate without its other side, so prisma
        validate runs at TASK level (after all the task's pieces).
        """
        if piece.kind == "prisma-model":
            return None, ""
        if piece.kind == "invariant" and piece.oracle:
            keep = _install(piece, code, self.ws)
            try:
                r = probe_mod.invariant_probe(
                    self.ws, piece.file, piece.oracle["signature"],
                    piece.oracle["cases"],
                    ref_expr=piece.oracle.get("ref_expr"))
            finally:
                _restore(keep, piece, self.ws)
            if not r.get("pass") and r.get("class") == "harness":
                return None, ""
            return bool(r.get("pass")), probe_mod.minimal_counterexample(r)
        return None, ""


def _install(piece, code: str, ws: Path) -> str | None:
    target = ws / piece.file
    prev = target.read_text() if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    if piece.kind == "prisma-model":
        body = prev if prev else _SCAFFOLD_HEAD
        import re
        name = piece.gate["models"][0]["name"]
        # declaration check must match `model X {` — never a comment that
        # merely mentions the model's name
        if re.search(rf"^model {name}\s*\{{", body, re.M):
            body = re.sub(rf"model {name}\s*\{{[\s\S]*?\n\}}", code, body,
                          count=1)
            target.write_text(body)
            return prev
        target.write_text(body.rstrip() + "\n\n" + code + "\n")
        return prev
    # route-handler: replace-or-append the handler (same semantics as
    # the controller's assembly; found when Track B accepted its first
    # route piece — mn-post — and crashed on the invariant branch)
    if piece.kind == "route-handler":
        import re
        body = prev or ""
        method = piece.gate["handlers"][0]
        if f"export async function {method}" in body:
            body = re.sub(
                rf"export async function {method}\b[\s\S]*?\n\}}",
                code, body, count=1)
            target.write_text(body)
            return prev
        if body.strip():
            target.write_text(body.rstrip() + "\n\n" + code + "\n")
            return prev
        head = ("import { NextRequest, NextResponse } from "
                "'next/server'\nimport { db } from '@/lib/db'\n\n")
        # invariant imports when the route uses them
        ir = piece.ir
        if ir:
            for h in ir.routes:
                if h.pid == piece.pid and h.uses_invariants:
                    mod = f"@/lib/{ir.app}/invariants"
                    fns = ", ".join(
                        i.signature.split("(")[0] for i in ir.invariants
                        if i.pid in h.uses_invariants)
                    head += f"import {{ {fns} }} from '{mod}'\n\n"
                    break
        target.write_text(head + code + "\n")
        return prev
    # invariant: append (dedup by function name)
    body = prev or ""
    fname = piece.oracle["signature"].split("(")[0]
    if f"function {fname}" in body:
        import re
        body = re.sub(rf"export function {fname}[\s\S]*?\n\}}", code, body,
                      count=1)
    else:
        body = (body.rstrip() + "\n\n" + code + "\n").lstrip()
    target.write_text(body)
    return prev


def _restore(prev: str | None, piece, ws: Path) -> None:
    target = ws / piece.file
    if prev is None:
        if target.exists():
            target.unlink()
    else:
        target.write_text(prev)


def run_baseline(model, piece, gates: _GateRunner, seed_base: int,
                 archive: Path) -> dict:
    """Session-036 Track-B: blind ladder, raw-gate feedback, no
    counterexamples, no forced continuation, burns the full budget."""
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
            # 036 s_fim_micro: tiny instruction adjacent to a gap
            prefix = piece.anchor
            suffix = ""
            out, usage = model.fim(prefix, suffix,
                                   instructions="fix this region",
                                   max_tokens=64, seed=seed + 3,
                                   stochastic=True)
            code = prompting.extract_construct(prefix + out, piece.kind)
        else:
            out, usage = model.generate(
                prompt, max_tokens=_max_tokens_for(piece), seed=seed,
                stochastic=(i % 2 == 1))
            code = prompting.extract_construct(piece.anchor + out,
                                               piece.kind)
        tokens += usage.get("tokens", 0)
        g = gates.structural(piece, code)
        probe_pass, ce = (None, "")
        if g["pass"]:
            probe_pass, ce = gates.behavioral(piece, code)
            if probe_pass is not False:
                resolved = True
                attempts.append({"i": i, "strat": strat,
                                 "tokens": usage.get("tokens", 0),
                                 "outcome": "accept"})
                _final_install(piece, code)
                break
        feedback = "\n".join(g.get("failures", [])[:6])
        attempts.append({
            "i": i, "strat": strat, "tokens": usage.get("tokens", 0),
            "gate_pass": g["pass"],
            "failures": g.get("failures", [])[:4],
            "near_empty": prompting.is_near_empty(code),
            "outcome": ("probe-reject" if g["pass"] else
                        "near-empty" if prompting.is_near_empty(code)
                        else "reject")})
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"base-{piece.pid}-{strat}-{i}-{seed}.json").write_text(
            json.dumps({"prompt": prompt, "candidate": code}, indent=1))
    return {"treatment": "baseline", "piece": piece.pid,
            "resolved": resolved, "attempts": len(attempts),
            "tokens": tokens,
            "detail": attempts}


def _final_install(piece, code: str) -> None:
    _install(piece, code, WS)


def _max_tokens_for(piece) -> int:
    return {"prisma-model": 300, "invariant": 200}.get(piece.kind, 450)


# --------------------------------------------------------- engine loop

def run_engine(model, piece, state: PolicyState, seed_base: int,
               ledger: Path, archive: Path, principles=None) -> dict:
    ctrl = PieceController(
        model, WS, piece, state,
        token_budget=BUDGET_TOKENS,
        ledger_path=ledger,
        archive_dir=archive,
        seed_base=seed_base,
        principles=principles)
    res = ctrl.run()
    res["treatment"] = "engine"
    return res


# -------------------------------------------------------------- main

def run_treatment(which: str, model, pieces, gates: _GateRunner,
                  shared_state: PolicyState, treatment: str, idx: int,
                  out: Path) -> list[dict]:
    """Run one treatment (baseline|engine) over all pieces of a task.
    Returns NORMALIZED results: {piece, resolved, attempts(int),
    tokens, detail(list)}."""
    results = []
    for piece in pieces:
        if treatment == "baseline":
            r = run_baseline(model, piece, gates,
                             seed_base=20000 + idx * 300,
                             archive=out / "baseline-gen")
            results.append({
                "piece": r["piece"], "resolved": r["resolved"],
                "attempts": r["attempts"], "tokens": r["tokens"],
                "detail": r["detail"]})
        else:
            r = run_engine(model, piece, shared_state,
                           seed_base=40000 + idx * 300,
                           ledger=out / "engine-ledger.jsonl",
                           archive=out / "engine-gen")
            results.append({
                "piece": r["piece"], "resolved": r["resolved"],
                "attempts": len(r["attempts"]),
                "tokens": r["tokens"],
                "detail": r["attempts"]})
    return results


def task_validates(pieces, results: list[dict]) -> dict:
    """Task-level behavioral check: every piece structurally resolved
    AND prisma accepts the assembled scratch schema."""
    if not pieces or any(p.kind != "prisma-model" for p in pieces):
        return {"pass": None}  # invariant tasks validate per-piece
    if not all(r["resolved"] for r in results):
        return {"pass": False, "failures": ["not all pieces resolved"]}
    return _prisma_validate(WS)


def run_curriculum(which: str, model, gates: _GateRunner,
                   shared_state: PolicyState,
                   task_range: tuple[int, int] | None = None) -> dict:
    tasks = CURRICULUM_A if which == "A" else CURRICULUM_B
    app = "curriculumA" if which == "A" else "curriculumB"
    out = OUT / which.lower()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    # resume support: load previously completed tasks from the partial
    lo, hi = task_range if task_range else (0, len(tasks))
    state_file = out / "progress.json"
    done: dict[str, dict] = {}
    if state_file.exists():
        done = json.loads(state_file.read_text())

    for idx, task in enumerate(tasks):
        if not (lo <= idx < hi):
            continue
        if task["pid"] in done:
            print(f"\n=== [{which}.{idx+1}] {task['pid']} — already "
                  f"complete (resume) ===", flush=True)
            results.append(done[task["pid"]])
            continue
        is_transfer = bool(task.get("cascade")) or "TRANSFER" in \
            task.get("label", "")
        tag = "transfer" if is_transfer else "dev"
        print(f"\n=== [{which}.{idx+1}] {task['pid']} ({task['label']}) "
              f"[{tag}] ===", flush=True)

        # build mini IR
        if which == "A":
            d = {"app": app, "concept": "A small relational store.",
                 "entities": [
                     {**e, "demo_domain": task["demo"]}
                     for e in task["entities"]],
                 "invariants": [], "routes": [], "ui": []}
        else:
            d = {"app": app, "concept": "A small logic library.",
                 "entities": [], "routes": [], "ui": [],
                 "invariants": [{k: v for k, v in task.items()
                                 if k in ("pid", "statement", "signature",
                                          "cases", "demo_domain",
                                          "ref_expr")}]}
        ir = taskir_from_dict(d)
        pieces = _retarget_schema_pieces(ir.pieces())

        # ---- baseline treatment: ALL pieces of the task, then the
        # task-level prisma validation on the assembled schema
        _reset_scratch(WS)
        base_res = run_treatment(which, model, pieces, gates,
                                 shared_state, "baseline", idx, out)
        base_val = task_validates(pieces, base_res)

        # ---- engine treatment: same pieces, shared learned state
        _reset_scratch(WS)
        eng_res = run_treatment(which, model, pieces, gates,
                                shared_state, "engine", idx, out)
        eng_val = task_validates(pieces, eng_res)

        base_ok = all(r["resolved"] for r in base_res) and \
            base_val.get("pass") is not False
        eng_ok = all(r["resolved"] for r in eng_res) and \
            eng_val.get("pass") is not False
        base_tok = sum(r["tokens"] for r in base_res)
        eng_tok = sum(r["tokens"] for r in eng_res)
        base_att = sum(r["attempts"] for r in base_res)
        eng_att = sum(r["attempts"] for r in eng_res)
        print(f"  baseline={'RESOLVED' if base_ok else 'failed  '} "
              f"({base_att} att, {base_tok} tok, validate="
              f"{base_val.get('pass')})   "
              f"engine={'RESOLVED' if eng_ok else 'failed  '} "
              f"({eng_att} att, {eng_tok} tok, validate="
              f"{eng_val.get('pass')})", flush=True)
        for r in base_res + eng_res:
            r.setdefault("detail", [])
        results.append({
            "task": task["pid"], "label": task["label"], "tag": tag,
            "pieces": [p.pid for p in pieces],
            "baseline": {"resolved": base_ok, "attempts": base_att,
                         "tokens": base_tok,
                         "validate": base_val.get("pass"),
                         "validate_failures": base_val.get("failures",
                                                            [])[:4],
                         "per_piece": [{"piece": r["piece"],
                                        "resolved": r["resolved"],
                                        "attempts": r["attempts"],
                                        "tokens": r["tokens"],
                                        "detail": r["detail"]}
                                       for r in base_res]},
            "engine": {"resolved": eng_ok, "attempts": eng_att,
                       "tokens": eng_tok,
                       "validate": eng_val.get("pass"),
                       "validate_failures": eng_val.get("failures", [])[:4],
                       "per_piece": [{"piece": r["piece"],
                                      "resolved": r["resolved"],
                                      "attempts": r["attempts"],
                                      "tokens": r["tokens"],
                                      "detail": r["detail"]}
                                     for r in eng_res]}})
        done[task["pid"]] = results[-1]
        state_file.write_text(json.dumps(done, indent=1))
        # incremental model-usage + policy-state checkpoint
        (out / "usage.json").write_text(json.dumps(model.usage()))
        (out / "policy-state.json").write_text(
            json.dumps(shared_state.snapshot()))

    # summary over EVERY completed task (resume-safe)
    all_results = [done[t["pid"]] for t in tasks if t["pid"] in done]
    dev = [r for r in all_results if r["tag"] == "dev"]
    tr = [r for r in all_results if r["tag"] == "transfer"]

    def _agg(rows):
        return {"n": len(rows),
                "baseline_resolved": sum(r["baseline"]["resolved"]
                                         for r in rows),
                "engine_resolved": sum(r["engine"]["resolved"] for r in rows),
                "baseline_tokens": sum(r["baseline"]["tokens"] for r in rows),
                "engine_tokens": sum(r["engine"]["tokens"] for r in rows),
                "baseline_attempts": sum(r["baseline"]["attempts"]
                                          for r in rows),
                "engine_attempts": sum(r["engine"]["attempts"]
                                        for r in rows)}

    summary = {
        "curriculum": which,
        "tasks_completed": len(all_results),
        "tasks_total": len(tasks),
        "dev": _agg(dev),
        "transfer": _agg(tr),
        "results": all_results}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main() -> None:
    which = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
    assert which in ("A", "B")
    rng = None
    if len(sys.argv) > 2:
        lo, hi = sys.argv[2].split("-")
        rng = (int(lo), int(hi))
    from archagent.model import FrozenModel
    try:
        from archagent.fullstack import devserver
        devserver.stop_dev()
    except Exception:
        pass
    model = FrozenModel(threads=2)
    gates = _GateRunner(WS)
    shared = PolicyState()
    # restore shared policy state when resuming
    st = OUT / which.lower() / "policy-state.json"
    if st.exists() and rng:
        d = json.loads(st.read_text())
        shared.kind_stats = d.get("kind_stats", {})
        shared.tokens_spent = d.get("tokens_spent", 0)
        shared.n_accepts = d.get("accepts", 0)
        shared.n_pieces = d.get("pieces", 0)
    t0 = time.time()
    summary = run_curriculum(which, model, gates, shared, task_range=rng)
    print(f"\n[{which}] DONE in {time.time()-t0:.0f}s")
    print(f"[{which}] dev: baseline {summary['dev']['baseline_resolved']}/"
          f"{summary['dev']['n']} vs engine "
          f"{summary['dev']['engine_resolved']}/{summary['dev']['n']}")
    print(f"[{which}] transfer: baseline "
          f"{summary['transfer']['baseline_resolved']}/"
          f"{summary['transfer']['n']} vs engine "
          f"{summary['transfer']['engine_resolved']}/"
          f"{summary['transfer']['n']}")
    print(f"[{which}] usage: {model.usage()}")


if __name__ == "__main__":
    main()
