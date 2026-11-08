"""SESSION 036 — PHASE 2 (TRUSTED-SCAFFOLD).

Contextual bandit for repair-strategy selection (Thompson sampling on
Beta posteriors, one arm per (error_category, strategy)).

This is a *general-strategy* learner: arms describe HOW to attempt a
repair (regenerate, complete a body, micro-FIM the gap, ...), never WHAT
the task-specific fix is.  There is no task-solution database anywhere
in this module.  Transfer is measured by whether preferences learned on
previous failures help on unfamiliar errors.

State is a small JSON dict — trivially within the CPU/RAM budget.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

STRATEGIES = [
    "regen_whole",       # direct source regeneration (fresh seed)
    "exact_shape",       # exact-shape whole-file contract (demo-complete)
    "body_completion",   # function-body completion with anchors
    "fim_micro",         # FIM micro-patch: <=15-word instruction by the gap
    "ast_replace",       # AST-constrained replacement of one node region
    "compiler_guided",   # tsc diagnostics fed into FIM around the error
    "doc_lookup",        # documentation excerpt + completion (Phase 4)
    "contract_split",    # decompose into single-expectation contracts
    "minimal_diff",      # change only the marked line(s)
]

CATEGORIES = [
    "syntax", "missing_export", "missing_literal", "missing_call",
    "wrong_contract", "demo_contamination", "type_error", "ui_state",
    "interface_mismatch",
]


class StrategyBandit:
    def __init__(self, state_path: str | None = None,
                 priors: dict | None = None, seed: int = 0):
        self.state_path = Path(state_path) if state_path else None
        self.rng = random.Random(seed)
        # (category, strategy) -> [alpha, beta]
        self.arms: dict[str, list[float]] = {}
        if self.state_path and self.state_path.exists():
            st = json.loads(self.state_path.read_text())
            self.arms = {k: list(v) for k, v in st.get("arms", {}).items()}
            self.history = list(st.get("history", []))
        else:
            self.history = []
            for c in CATEGORIES:
                for s in STRATEGIES:
                    a, b = 1.0, 1.0
                    if priors:
                        p = priors.get(c, {}).get(s)
                        if p:
                            # p = [successes, failures] observed historically;
                            # discounted by half so the new task can override
                            a = 1.0 + 0.5 * p[0]
                            b = 1.0 + 0.5 * p[1]
                    self.arms[f"{c}|{s}"] = [a, b]

    # -- selection -------------------------------------------------------

    def sample(self, category: str, allowed: list[str] | None = None
               ) -> tuple[str, dict]:
        """Thompson-sample a strategy for this error category.

        Returns (strategy, why) where `why` carries the posterior means
        for the record (the controller logs WHY a strategy was chosen).
        """
        pool = allowed or STRATEGIES
        best, best_draw, means = None, -1.0, {}
        for s in pool:
            a, b = self.arms.get(f"{category}|{s}", [1.0, 1.0])
            draw = self.rng.betavariate(
                max(a, 0.01), max(b, 0.01))
            means[s] = round(a / (a + b), 3)
            if draw > best_draw:
                best, best_draw = s, draw
        why = {
            "posterior_means": means,
            "thompson_draw": round(best_draw, 3),
            "pool": list(pool),
        }
        return best, why

    def posterior(self, category: str) -> dict:
        return {s: round(self.arms.get(f"{category}|{s}", [1, 1])[0]
                         / sum(self.arms.get(f"{category}|{s}", [1, 1])), 3)
                for s in STRATEGIES}

    # -- update ----------------------------------------------------------

    def update(self, category: str, strategy: str, success: bool) -> dict:
        key = f"{category}|{strategy}"
        a, b = self.arms.setdefault(key, [1.0, 1.0])
        if success:
            self.arms[key] = [a + 1.0, b]
        else:
            self.arms[key] = [a, b + 1.0]
        rec = {
            "category": category, "strategy": strategy,
            "success": success,
            "posterior_after": round(
                self.arms[key][0] / sum(self.arms[key]), 3),
        }
        self.history.append(rec)
        return rec

    def save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "arms": {k: v for k, v in self.arms.items()},
            "history": self.history[-2000:],
        }, indent=1))

    def snapshot_table(self) -> dict:
        """category -> {strategy: posterior mean} for reports/ablation."""
        out = {}
        for c in CATEGORIES:
            out[c] = self.posterior(c)
        return out
