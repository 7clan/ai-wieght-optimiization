"""SESSION 038A — PHASE 2b/2c: fresh-suite retest of the invariant
repair package (fixed baseline vs repaired engine).

WHAT THE 037 REPORT CLAIMED VS WHAT THE ARCHIVES SHOW
-----------------------------------------------------
Session 037 attributed its invariant losses to "the engine's 200-token
invariant cap truncating correct predicates".  Session-038A archive
forensics (Phase 2 pre-work, evidence in the final report) found the
decomposition was different:

  * Track C's clean re-run generated a COMPLETE, gate-passing,
    behaviorally-correct 251-char ap-transition predicate at step 0 —
    and the harness threw it away: the probes-disabled monkeypatch
    returns {"pass": None} and the controller recorded
    bool(None) == False  ->  "probe-reject"  ->  never installed
    (final score: "file missing").  HARNESS DEFECT, not a model or
    cap failure.
  * The 037 invariant probe emits TWO PROBE-RESULT lines when the
    property fuzz fails (false, then an unconditional true); the
    runner takes the last line, so fuzz enforcement was silently
    masked in EVERY 037 run (over-acceptance direction).
  * Track D's clean re-run genuinely failed to generate correct
    predicates at its seeds (prompt-echo loops) — generation-shape
    failures, where the 200-token cap and prose-echo extraction
    contributed (the original run-1 mn-window exhibit).

THE REPAIR PACKAGE (all declared; total budget unchanged)
---------------------------------------------------------
  P1  probe-disable semantics: {"pass": None} is "no probe", never
      False (forked controller loop).
  P2  in-loop invariant probes use the fresh seeded, type-aware,
      single-verdict probe (archagent.finetune.replay.invariant_probe)
      instead of the double-emit interval-only fuzz.
  P3  invariant generation cap 200 -> 300 tokens (per-attempt cap
      only; the per-piece TOTAL budget stays 2000 tokens / 6
      generations for BOTH tracks).
  P4  mechanical prompt-echo stripping on extracted candidates
      (fixed instruction sentences + duplicated anchor echoes are
      removed; nothing is added, raw outputs archived alongside).

COMPARISON DESIGN
-----------------
  Track B  fixed baseline — the exact Session-036 Track-B treatment
           (ladder [exact_shape x4, regen_whole x2, fim_micro x2],
           520-token cap, structural gates only in-loop).
  Track R  repaired engine — the Session-037 PieceController forked
           with P1-P4 (probes + counterexamples + budget-aware policy).

  Same checkpoint, SAME per-piece seeds for both tracks, same frozen
  contracts (archagent/z038a/suite.py, sha ffff91b5... frozen before
  any generation), same 2000-token/6-attempt totals, same 2-CPU box,
  sequential single-loaded model.

  Per track AND domain: schema file, invariant files, route files and
  probe databases are reset (the Session-037 cross-track-contamination
  lesson).  Final scoring is independent of both loops: structural
  gates + prisma validate + task-level db push + LIVE route probes on
  fresh databases (a no-verdict route probe is NOT a pass) + seeded
  case/fuzz invariant probes.

Usage:
  ARCHAGENT_MODEL_DIR=/home/z/models/qwen25-coder-05b \
    python -m archagent.z038a.retest [--only B|R] [--limit-domains N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize.controller import (  # noqa: E402
    PieceController, _SCHEMA_HEAD, _model_name, _sha, VERIFY,
    NODE_ENV_PATH)
from archagent.generalize import prompting  # noqa: E402
from archagent.generalize import probe as probe_mod  # noqa: E402
from archagent.generalize.run_curricula import (  # noqa: E402
    baseline_prompt, _install)
from archagent.generalize.run_tracks import _GateRunner  # noqa: E402
from archagent.finetune.replay import invariant_probe as fresh_probe  # noqa: E402
from archagent.z038a.suite import DOMAINS, manifest as suite_manifest  # noqa: E402

WS = Path("/home/z/my-project")
OUT = ROOT / "experiments/z038a-independent-retest/retest"
INV_FILE = "src/lib/{app}/invariants.ts"
BUDGET_TOKENS = 2000
BUDGET_ATTEMPTS = 6
BASELINE_LADDER = (["exact_shape"] * 4 + ["regen_whole"] * 2
                   + ["fim_micro"] * 2)

# P4: the fixed instruction sentences that the 0.5B model echoes into
# its continuations (all drawn verbatim from the prompt templates).
_ECHO_PATTERNS = [
    r"The first line is already written; continue from it:?",
    r"Write the complete (?:invariant|file|model|route|function) now\.?",
    r"Continue writing the construct body now, starting with its "
    r"first statement:?",
    r"Adapt the example's PATTERNS to this task's names[^.]*\.",
    r"Your last attempt stopped before writing anything\.?",
    r"Now YOUR task:.*",
    r"You may use the PATTERNS from the requirements above\.?",
    r"The file may hold several such functions; add this one\.?",
    r"The automated checks reported:?",
    r"Fix exactly that\.?",
    r"Also include a complete example for each case\.?",
    r"// write the test case.*",
    r"// test case for the predicate.*",
    r"// \[TEA-\d+\].*",
]


def strip_prompt_echo(code: str) -> str:
    """P4: mechanical removal of fixed prompt-echo lines (nothing is
    added; raw model output is archived unmodified alongside)."""
    out_lines = []
    for line in code.splitlines():
        s = line.strip()
        if any(re.fullmatch(p, s) for p in _ECHO_PATTERNS):
            continue
        out_lines.append(line)
    t = "\n".join(out_lines)
    # duplicated anchor echo: the construct opener appearing twice in
    # a row (anchor + model re-echoing it)
    t = re.sub(r"(export function \w+\()[^\n]*\n\s*\1", r"\1", t)
    return t.strip("\n")


# ------------------------------------------------------------ baseline

def run_track_b(model, piece, gates: _GateRunner, seed_base: int,
                archive: Path) -> dict:
    """The EXACT Session-036/037 Track-B treatment (copied from
    run_tracks.run_track_b; only the seed scheme differs — shared with
    Track R for paired comparison)."""
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


# ------------------------------------------------------ repaired engine

class RepairedController(PieceController):
    """Session-037 PieceController forked with the declared repair
    package P1-P4.  The run() loop is re-implemented here (the 037
    file stays untouched for its own reproducibility); every deviation
    is marked [P1]/[P2]/[P3]/[P4] below.
    """

    def _max_tokens(self) -> int:
        caps = {"prisma-model": 300, "type-interface": 220,
                "invariant": 300,  # [P3] was 200
                "route-handler": 520, "hook": 420,
                "component": 560, "page": 700}
        return caps.get(self.piece.kind, 450)

    def _generate(self, action, seed, failing, counterexample,
                  current_construct=""):
        code, usage, prompt, mode = super()._generate(
            action, seed, failing, counterexample,
            current_construct=current_construct)
        raw = code
        code = strip_prompt_echo(code)          # [P4]
        if not code.strip():
            code = raw                          # never empty the candidate
        self._last_raw = raw
        return code, usage, prompt, mode

    def _behavioral_probe(self, code: str) -> dict:
        o = self.piece.oracle
        if o.get("probe") == "route":
            keep = self._install_candidate(code)
            try:
                return probe_mod.route_probe(
                    self.ws, self.piece.file, o["method"],
                    o.get("cases", []), seed=o.get("seed"))
            finally:
                self._restore(keep)
        if o.get("signature"):
            # [P2] fresh seeded type-aware single-verdict probe
            import tempfile
            with tempfile.TemporaryDirectory(prefix="z038a-inv-") as td:
                return fresh_probe(code, o, Path(td))
        return {"pass": None}

    def _archive(self, step, action, seed, prompt, code):
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        raw = getattr(self, "_last_raw", code)
        (self.archive_dir /
         f"{self.piece.pid}-{action}-{step}-{seed}.json").write_text(
            json.dumps({"prompt": prompt, "candidate": code,
                        "raw_model_output": raw}, indent=1))

    def run(self) -> dict:
        """037 controller.run() fork.  [P1]: probe results use
        tri-state semantics — None (no probe / no verdict) never
        rejects a candidate."""
        t0 = time.time()
        near_empty = False
        structural_pass = False
        failing: list[str] = []
        probe_pass = None
        counterexample = ""
        current_construct = ""
        accepted = None

        for step in range(24):
            dec = self.policy.next_action(
                near_empty=near_empty,
                structural_pass=structural_pass,
                failing_clauses=failing,
                probe_pass=probe_pass)
            if dec.action == "stop":
                self.attempts.append({"step": step, "action": "stop",
                                      "reason": dec.reason})
                break
            if dec.action == "accept":
                accepted = {"code": current_construct, "action": dec.action,
                            "attempts": step + 1}
                break

            seed = self.seed_base + step * 31
            try:
                code, usage, prompt, mode = self._generate(
                    dec.action, seed, failing, counterexample,
                    current_construct=current_construct)
            except Exception as e:
                self.attempts.append({
                    "step": step, "action": dec.action,
                    "outcome": "harness-error", "error": str(e)[:200]})
                break

            near_empty = prompting.is_near_empty(code)
            candidate_sha = _sha(code)
            if self.policy.is_duplicate(candidate_sha):
                self._archive(step, dec.action, seed, prompt, code)
                self.attempts.append({
                    "step": step, "action": dec.action, "mode": mode,
                    "seed": seed, "tokens": usage.get("tokens", 0),
                    "outcome": "dedup-duplicate"})
                self.policy.observe(
                    action=dec.action, candidate_sha=candidate_sha,
                    failing_clauses=[], tokens=usage.get("tokens", 0),
                    duplicate=True)
                continue

            gate = self._structural_gate(code)
            structural_pass = bool(gate["pass"])
            failing = [f for f in gate.get("failures", [])
                       if not f.startswith("parse:")]
            parse_fail = [f for f in gate.get("failures", [])
                          if f.startswith("parse:")]

            probe_pass = None            # [P1] tri-state
            if structural_pass and self.piece.oracle:
                pr = self._behavioral_probe(code)
                got = pr.get("pass")
                cls = pr.get("class")
                if got is None or (got is False and cls == "harness"):
                    # [P1] no verdict OR harness-class defect -> never
                    # reject a candidate on it (037 semantics, fixed)
                    probe_pass = None
                else:
                    probe_pass = bool(got)
                    if not probe_pass:
                        counterexample = probe_mod.minimal_counterexample(pr)

            rec = {
                "step": step, "action": dec.action, "mode": mode,
                "seed": seed, "tokens": usage.get("tokens", 0),
                "seconds": usage.get("seconds", 0),
                "prompt_sha": _sha(prompt), "candidate_sha": candidate_sha,
                "near_empty": near_empty,
                "gate": {"pass": structural_pass,
                         "failures": (parse_fail + failing)[:6]},
                "probe": ({"pass": probe_pass,
                           "counterexample": counterexample[:200]}
                          if self.piece.oracle else None),
                "policy_reason": dec.reason,
                "outcome": ("accept" if structural_pass and
                            probe_pass is not False else
                            "near-empty" if near_empty else
                            "parse-reject" if parse_fail else
                            "clause-reject" if failing else
                            "probe-reject"),
            }
            self.attempts.append(rec)
            self._archive(step, dec.action, seed, prompt, code)
            current_construct = code
            self._last_failures = (parse_fail + failing)[:6]
            self.policy.observe(
                action=dec.action, candidate_sha=candidate_sha,
                failing_clauses=(parse_fail + failing),
                tokens=usage.get("tokens", 0),
                success=(structural_pass and probe_pass is not False),
                near_empty=near_empty)
            if structural_pass and probe_pass is not False:
                accepted = {"code": code, "action": dec.action,
                            "attempts": step + 1}
                break

        result = {
            "piece": self.piece.pid, "kind": self.piece.kind,
            "file": self.piece.file,
            "resolved": accepted is not None,
            "attempts": self.attempts,
            "tokens": sum(a.get("tokens", 0) for a in self.attempts
                          if isinstance(a.get("tokens"), int)),
            "seconds": round(time.time() - t0, 1),
            "policy_log": [d.__dict__ for d in self.policy.log],
        }
        if accepted is not None:
            self._install_candidate(accepted["code"])
        with open(self.ledger_path, "a") as fh:
            fh.write(json.dumps(result) + "\n")
        return result


# ---------------------------------------------------- final scoring

def final_score(pieces, gates: _GateRunner, db_url: str | None) -> dict:
    """Independent verification of INSTALLED files.  Stricter than 037:
    a route probe that produces no verdict is NOT a pass."""
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
            m = re.search(rf"model {name}\s*\{{[\s\S]*?\n\}}", code)
            if not m:
                out["pieces"][p.pid] = {"resolved": False,
                                        "reason": "model missing"}
                continue
            code = m.group(0)
        elif p.kind == "route-handler":
            method = p.gate["handlers"][0]
            m = re.search(
                rf"export async function {method}\b[\s\S]*?\n\}}", code)
            if not m:
                out["pieces"][p.pid] = {"resolved": False,
                                        "reason": "handler missing"}
                continue
            code = m.group(0)
        elif p.kind == "invariant":
            fname = p.oracle["signature"].split("(")[0]
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
            if p.kind == "invariant":
                import tempfile
                with tempfile.TemporaryDirectory(prefix="z038a-fs-") as td:
                    r = fresh_probe(code, p.oracle, Path(td))
                if r.get("class") == "harness":
                    rec["behavioral"] = None
                    rec["resolved"] = False   # no verdict != pass
                    rec["reason"] = "probe no-verdict (harness)"
                else:
                    rec["behavioral"] = bool(r.get("pass"))
                    if not r.get("pass"):
                        rec["resolved"] = False
                        rec["ce"] = probe_mod.minimal_counterexample(r)
            elif p.kind == "route-handler" and p.oracle.get("cases"):
                r = probe_mod.route_probe(
                    WS, p.file, p.oracle["method"], p.oracle["cases"],
                    seed=p.oracle.get("seed"), db_url=db_url)
                if r.get("class") == "harness" or r.get("pass") is None:
                    rec["behavioral"] = None
                    rec["resolved"] = False   # no verdict != pass
                    rec["reason"] = "probe no-verdict (harness)"
                else:
                    rec["behavioral"] = bool(r.get("pass"))
                    if not r.get("pass"):
                        rec["resolved"] = False
                        rec["failures"] = r.get("failures", [])[:4]
        out["pieces"][p.pid] = rec
        out["resolved"] += int(rec["resolved"])
    return out


def prisma_validate_and_generate() -> bool:
    try:
        r = subprocess.run(
            ["bunx", "--bun", "prisma", "validate", "--schema",
             "prisma/schema.prisma"],
            capture_output=True, text=True, timeout=180, cwd=str(WS),
            env={**os.environ, "DATABASE_URL": "file:./db/z038a-tmp.db"})
        return r.returncode == 0 and "is valid" in (r.stdout + r.stderr)
    except Exception:
        return False


def _push_and_generate() -> None:
    """db push (with client generation) against the currently
    installed schema, into a throwaway staging database."""
    dbf = WS / "db" / "z038a-staging.db"
    if dbf.exists():
        dbf.unlink()
    subprocess.run(
        ["bunx", "--bun", "prisma", "db", "push", "--schema",
         "prisma/schema.prisma"],
        capture_output=True, timeout=240, cwd=str(WS),
        env={**os.environ, "DATABASE_URL": f"file:{dbf}"})


# ------------------------------------------------------------- runner

def pieces_of_domain(d: dict):
    ir = taskir_from_dict(d)
    pieces = ir.pieces()
    for p in pieces:
        if p.kind == "prisma-model":
            p.file = "prisma/schema.prisma"
        if p.kind == "invariant":
            p.file = INV_FILE.format(app=d["app"])
    return pieces


def reset_domain_state(dom: dict, pieces) -> None:
    """Clean installed/generated files + DB state per track AND domain
    (Session-037 cross-track-contamination lesson)."""
    (WS / "prisma/schema.prisma").write_text(_SCHEMA_HEAD)
    inv = WS / INV_FILE.format(app=dom["app"])
    if inv.exists():
        inv.unlink()
    for p in pieces:
        if p.kind == "route-handler":
            t = WS / p.file
            if t.exists():
                t.unlink()


def run_track(track: str, model, gates: _GateRunner) -> dict:
    out = OUT / track
    out.mkdir(parents=True, exist_ok=True)
    shared = PolicyState()
    results = []
    t0 = time.time()
    for di, dom in enumerate(DOMAINS):
        print(f"\n=== [{track}] domain {dom['app']} ===", flush=True)
        pieces = pieces_of_domain(dom)
        reset_domain_state(dom, pieces)
        dom_results = []
        # DEPENDENCY STAGING (smoke-run fix, disclosed): the prisma
        # pieces must be installed and the client regenerated BEFORE
        # any route piece runs — in-loop route probes import the
        # workspace client, and a stale client makes db.<model>
        # undefined (seeding TypeError).  Session 037 never hit this
        # because its in-loop route probes uniformly returned
        # no-verdict (the pre-2c5f098 template bug).
        prisma_pieces = [p for p in pieces if p.kind == "prisma-model"]
        other_pieces = [p for p in pieces if p.kind != "prisma-model"]
        staged = False
        for pi, piece in enumerate(pieces):
            # SHARED per-piece seed base for both tracks (paired)
            seed_base = 200000 + di * 5000 + pi * 300
            if not staged and other_pieces and piece is other_pieces[0]:
                _push_and_generate()
                staged = True
            if track == "B":
                res = run_track_b(model, piece, gates, seed_base,
                                  out / "gen")
            else:
                ctrl = RepairedController(
                    model, WS, piece, shared,
                    token_budget=BUDGET_TOKENS,
                    ledger_path=out / "ledger.jsonl",
                    archive_dir=out / "gen",
                    seed_base=seed_base)
                res = ctrl.run()
            dom_results.append(res)
            n_att = res["attempts"] if isinstance(res["attempts"], int) \
                else len(res["attempts"])
            print(f"  piece {piece.pid:14s} loop-resolved="
                  f"{'Y' if res['resolved'] else 'N'} "
                  f"({n_att} att, {res['tokens']} tok)", flush=True)

        ok = prisma_validate_and_generate()
        dbf = WS / "db" / f"z038a-{dom['app']}-{track}.db"
        if dbf.exists():
            dbf.unlink()
        subprocess.run(
            ["bunx", "--bun", "prisma", "db", "push", "--schema",
             "prisma/schema.prisma"],
            capture_output=True, timeout=240, cwd=str(WS),
            env={**os.environ,
                 "DATABASE_URL": f"file:{dbf}"})
        fs = final_score(pieces, gates, db_url=f"file:{dbf}")
        results.append({
            "domain": dom["app"], "schema_validates": ok,
            "final_resolved": fs["resolved"], "total": fs["total"],
            "per_piece": fs["pieces"],
            "loop": [{k: r[k] for k in ("piece", "resolved", "tokens")}
                     for r in dom_results],
            "loop_tokens": sum(r["tokens"] for r in dom_results),
        })
        print(f"  FINAL {fs['resolved']}/{fs['total']} "
              f"(schema {'ok' if ok else 'INVALID'})", flush=True)

    return {
        "track": track,
        "wall_seconds": round(time.time() - t0, 1),
        "domains": results,
        "final_total": sum(r["final_resolved"] for r in results),
        "n_pieces": sum(r["total"] for r in results),
        "loop_tokens": sum(r["loop_tokens"] for r in results),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["B", "R"], default=None)
    ap.add_argument("--limit-domains", type=int, default=None)
    args = ap.parse_args()

    # freeze check BEFORE any generation
    m = suite_manifest()
    frozen = json.loads((ROOT / "experiments/z038a-independent-retest/"
                         "suite/MANIFEST.json").read_text())
    if m["suite_sha256"] != frozen["suite_sha256"]:
        raise SystemExit("SUITE DRIFT after freeze — refusing to run")
    if args.limit_domains:
        import archagent.z038a.suite as S
        S.DOMAINS[:] = S.DOMAINS[:args.limit_domains]
        global DOMAINS
        DOMAINS = S.DOMAINS

    os.environ.setdefault("ARCHAGENT_MODEL_DIR",
                          "/home/z/models/qwen25-coder-05b")
    from archagent.model import FrozenModel
    model = FrozenModel()
    gates = _GateRunner(WS)

    tracks = []
    for t in (["B", "R"] if args.only is None else [args.only]):
        summary = run_track(t, model, gates)
        summary["peak_rss_kib"] = resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss
        tracks.append(summary)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"summary-{t}.json").write_text(
            json.dumps(summary, indent=1) + "\n", encoding="utf-8")
        print(f"\n[{t}] TOTAL {summary['final_total']}/"
              f"{summary['n_pieces']} | loop tokens "
              f"{summary['loop_tokens']} | wall "
              f"{summary['wall_seconds']}s", flush=True)

    if len(tracks) == 2:
        b, r = tracks
        print("\n=== PAIRED COMPARISON (fresh suite) ===")
        for dom_b, dom_r in zip(b["domains"], r["domains"]):
            for pid in dom_b["per_piece"]:
                pb = dom_b["per_piece"][pid]["resolved"]
                pr_ = dom_r["per_piece"][pid]["resolved"]
                print(f"  {pid:14s} B={'Y' if pb else 'n'} "
                      f"R={'Y' if pr_ else 'n'}"
                      f"{'  <- R wins' if pr_ and not pb else ''}"
                      f"{'  <- B wins' if pb and not pr_ else ''}")
        print(f"B: {b['final_total']}/{b['n_pieces']} "
              f"({b['loop_tokens']} tok)  vs  "
              f"R: {r['final_total']}/{r['n_pieces']} "
              f"({r['loop_tokens']} tok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
