"""SESSION 036 — PHASE 2/3 (TRUSTED-SCAFFOLD).

Adaptive repair controller.

Loop per defect:
  1. diagnose (structural gate failures + tsc) -> general error category
  2. Thompson-sample a repair strategy from the category's arms
  3. run the strategy -> candidate patch (original file preserved)
  4. verify: structural gates -> scoped tsc -> (optional) isolated tests
  5. keep or revert on evidence; regressions always rejected
  6. update the bandit; append the full ledger record

Every attempt records: diagnosed failure, strategy, why it was selected,
the attempted correction (prompt + completion sha), the actual result,
and the policy update.  Provenance levels are kept separate — L1
(Qwen-chosen) successes are NEVER blended with L2/L3/L4.

Fixed-strategy ablation: `fixed_ladder=True` replaces step 2 with the
Session-035 escalation order (exact_shape -> body_completion -> fim_micro),
identical budgets, for the Track-B comparison.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .bandit import StrategyBandit, STRATEGIES
from .categories import categorize
from . import strategies as S

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "archagent" / "verify" / "run_gates.mjs"

FIXED_LADDER = ["exact_shape", "body_completion", "fim_micro"]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class RepairController:
    def __init__(self, model, workspace: str, ledger_path: str,
                 state_path: str | None = None, priors: dict | None = None,
                 bandit_seed: int = 0, budget_per_defect: int = 12,
                 fixed_ladder: bool = False, tsc_per_attempt: bool = False,
                 archive_dir: str | None = None):
        self.model = model
        self.ws = Path(workspace)
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.bandit = StrategyBandit(state_path, priors=priors,
                                     seed=bandit_seed)
        self.budget = budget_per_defect
        self.fixed_ladder = fixed_ladder
        self.tsc_per_attempt = tsc_per_attempt
        self.archive_dir = (Path(archive_dir) if archive_dir
                            else Path(str(ledger_path) + ".archive"))
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.ledger: list[dict] = []
        self._attempt_counter = 0
        self.tsc_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------ gates

    def structural_gate(self, code: str, contract: dict) -> dict:
        """Run the Phase-1 AST gates on candidate code (stdin mode)."""
        cf = self.ws / ".repair-contract.json"
        cf.write_text(json.dumps(contract))
        try:
            r = subprocess.run(
                ["node", str(VERIFY), "--contract", str(cf), "--stdin"],
                input=code, capture_output=True, text=True, timeout=90,
                cwd=str(self.ws), env={**os.environ,
                    "NODE_PATH": "/home/z/my-project/node_modules"})
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception as e:  # harness failure — never counts vs the app
            return {"pass": False, "failures": [f"harness error: {e}"]}

    def tsc_gate(self) -> list[str]:
        """Scoped compile gate (Session-035 tsconfig.gate.json)."""
        try:
            r = subprocess.run(
                ["node_modules/.bin/tsc", "--noEmit", "-p",
                 "tsconfig.gate.json"],
                capture_output=True, text=True, timeout=300,
                cwd=str(self.ws))
            if r.returncode == 0:
                return []
            return [l for l in (r.stdout + r.stderr).splitlines()
                    if "error TS" in l][:20]
        except Exception as e:
            return [f"harness error (tsc): {e}"]

    def run_isolated_tests(self, probe) -> tuple[bool, list[str]]:
        """Run ONLY the relevant dynamic tests for this defect.

        `probe(code_already_installed) -> (pass, failures)` — supplied by
        the caller (e.g. one API check or a scoped UI probe).  Runs with
        the patch installed; the caller reinstalls the original on
        failure via revert().
        """
        try:
            return probe(True)
        except Exception as e:
            return False, [f"probe harness error: {e}"]

    # ----------------------------------------------------------- repair

    def repair(self, defect: dict, probe=None, docs: str = "",
               named_fix: str = "", seed_base: int = 1000) -> dict:
        """Attempt to repair one defect within the budget.

        defect: {file, code, contract, gate_failures, tsc_errors?,
                 dynamic_failures?, region?, concept?}
        Returns a result dict; the workspace is only mutated on KEEP.
        """
        original = defect["code"]
        category = categorize(defect.get("gate_failures", []),
                              defect.get("tsc_errors"),
                              defect.get("dynamic_failures"))
        attempts = []
        kept = None
        t_start = time.time()

        order = []
        for i in range(self.budget):
            if self.fixed_ladder:
                strat = FIXED_LADDER[min(i // 4, len(FIXED_LADDER) - 1)]
                why = {"mode": "fixed-ladder (ablation)",
                       "index": i}
            else:
                strat, why = self.bandit.sample(
                    category, allowed=[s for s in STRATEGIES
                                       if s != "apply_named"])
                why["mode"] = "adaptive"
            order.append(strat)

            seed = seed_base + i * 17
            d = {**defect, "category": category}
            try:
                code, usage, prompt, prov = S.run_strategy(
                    self.model, strat, d, seed, docs=docs,
                    named_fix=named_fix)
                # PROVENANCE DISCIPLINE (Session 036): if the diagnosis
                # literally names the missing code, the model is APPLYING
                # a named fix (L2), not choosing it (L1).  Semantic
                # diagnoses keep L1.
                if prov == "L1" and not d.get("diagnosis"):
                    # no semantic diagnosis => instructions derived from
                    # mechanical failures that may quote expected code
                    prov = "L2-diagnosis"
            except Exception as e:
                attempts.append({"strategy": strat, "error": str(e)[:200],
                                 "outcome": "strategy-error"})
                self.bandit.update(category, strat, False)
                continue

            gate = self.structural_gate(code, defect["contract"])
            tsc = (self.tsc_gate() if gate["pass"] and self.tsc_per_attempt
                   else [])
            passed = gate["pass"] and not tsc
            reason = "pass" if passed else (
                "; ".join(gate["failures"][:3]) if not gate["pass"]
                else "; ".join(tsc[:3]))

            rec = {
                "attempt": i + 1, "category": category, "strategy": strat,
                "archive": self._archive_attempt(
                    d, strat, seed, prompt, code, i),
                "why_selected": why,
                "provenance": prov,
                "seed": seed, "usage": usage,
                "prompt_sha": _sha(prompt),
                "candidate_sha": _sha(code),
                "diff_bytes": abs(len(code) - len(original)),
                "gate": gate, "tsc": tsc[:5],
                "outcome": "structural-pass" if passed else f"reject: {reason}",
            }
            attempts.append(rec)
            self.bandit.update(category, strat, passed)

            if passed:
                if probe is not None:
                    # install, probe, and revert on regression
                    self._install(defect["file"], code)
                    ok, failures = self.run_isolated_tests(probe)
                    if not ok:
                        rec["outcome"] = f"regression: {failures[:2]}"
                        self._install(defect["file"], original)
                        self.bandit.update(category, strat, False)
                        continue
                    rec["probe"] = "pass"
                kept = {"file": defect["file"], "code": code,
                        "strategy": strat, "provenance": prov,
                        "attempts": i + 1}
                self._install(defect["file"], code)
                break

        result = {
            "file": defect["file"],
            "category": category,
            "mode": "fixed" if self.fixed_ladder else "adaptive",
            "resolved": kept is not None,
            "strategy_order": order,
            "attempts": attempts,
            "resolved_by": kept["strategy"] if kept else None,
            "provenance": kept["provenance"] if kept else None,
            "seconds": round(time.time() - t_start, 1),
            "tokens": sum(a.get("usage", {}).get("tokens", 0)
                          for a in attempts if isinstance(a.get("usage"), dict)),
        }
        self.ledger.append(result)
        self._append_ledger(result)
        self.bandit.save()
        return result

    def _archive_attempt(self, defect: dict, strat: str, seed: int,
                         prompt: str, code: str, i: int) -> str:
        slug = re.sub(r"[^\w]+", "-", defect["file"])[:60]
        name = f"{slug}-{strat}-{i}-{seed}.json"
        p = self.archive_dir / name
        p.write_text(json.dumps({
            "file": defect["file"], "strategy": strat, "seed": seed,
            "prompt": prompt, "candidate": code,
            "gate_failures": defect.get("gate_failures", []),
        }, indent=1))
        return name

    def _install(self, rel: str, code: str) -> None:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code)

    def _append_ledger(self, result: dict) -> None:
        with open(self.ledger_path, "a") as fh:
            fh.write(json.dumps(result) + "\n")

    def summary(self) -> dict:
        n = len(self.ledger)
        resolved = sum(1 for r in self.ledger if r["resolved"])
        by_cat: dict[str, dict] = {}
        for r in self.ledger:
            c = by_cat.setdefault(r["category"],
                                  {"defects": 0, "resolved": 0,
                                   "generations": 0})
            c["defects"] += 1
            c["resolved"] += int(r["resolved"])
            c["generations"] += len(r["attempts"])
        return {"defects": n, "resolved": resolved,
                "by_category": by_cat,
                "bandit": self.bandit.snapshot_table()}
