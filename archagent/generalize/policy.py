"""SESSION 037 — PHASE 3: the budget-aware conservative policy.

Replaces Session-036's Thompson-sampling bandit (which lost 4/12 vs
7/12).  Phase-1 root causes addressed:

  * 7/9 arms started uniform Beta(1,1) — here the ladder is FIXED by
    evidence and exploration is never required to find the winner;
  * binary reward hid near-misses — here closeness (passing-clause
    count) drives escalation and stopping;
  * degenerate strategies consumed 53/87 attempts — here only strategies
    VALID for the piece kind are armed;
  * no early-EOS mitigation — near-empty candidates trigger a forced-
    continuation retry, not a strategy failure.

State machine per piece (deterministic, seeded only in generation):

    exact_shape ──near-empty──▶ forced-continuation
        │
        ├─ structural pass ──▶ behavioral probe ──pass──▶ ACCEPT
        │                                          └─fail─▶ micro-repair×R
        ├─ near-miss (≤2 clauses) ──▶ micro-repair×R
        └─ far-miss ──▶ exact_shape+feedback ──▶ decompose (clause-FIM)

Stop rules: budget exhausted; failure signature unchanged after 3
attempts; closeness non-improving over 2 attempts with repair budget
spent.  Every decision is ledgered with its reason.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

NEAR_MISS_CLAUSES = 2          # ≤2 failing clauses => micro-repair
MAX_MICRO_REPAIRS = 3
MAX_SAME_SIGNATURE = 3
MAX_FLAT_CLOSNESS = 2

# Evidence-backed default ladder per piece kind (Phase-1 Table).
LADDERS: dict[str, list[str]] = {
    # route/invariant/component pieces: whole-construct first (the only
    # mode whose prompts were valid in 036), then feedback, then
    # decomposition.
    "prisma-model":   ["exact_shape", "exact_shape_feedback", "decompose"],
    "type-interface": ["exact_shape", "exact_shape_feedback"],
    "invariant":      ["exact_shape", "exact_shape_feedback", "decompose"],
    "route-handler":  ["exact_shape", "exact_shape_feedback", "decompose"],
    "hook":           ["exact_shape", "exact_shape_feedback"],
    "component":      ["exact_shape", "exact_shape_feedback"],
    "page":           ["exact_shape", "exact_shape_feedback", "decompose"],
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


@dataclass
class Decision:
    attempt_no: int
    action: str            # exact_shape|forced_continuation|micro_repair|
                           # decompose|accept|stop
    reason: str
    strategy: str = ""
    est_cost_tokens: int = 0


@dataclass
class PolicyState:
    """Carried across pieces within one track run (amortization), and
    persistable for analysis."""
    kind_stats: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    signature_counts: dict[str, int] = field(default_factory=dict)
    tokens_spent: int = 0
    n_accepts: int = 0
    n_pieces: int = 0

    def record(self, kind: str, strategy: str, success: bool,
               tokens: int) -> None:
        st = self.kind_stats.setdefault(kind, {}).setdefault(
            strategy, [0, 0])
        st[0 if success else 1] += 1
        self.tokens_spent += tokens
        self.n_accepts += int(success)

    def demoted(self, kind: str) -> set[str]:
        """Strategies with >=2 failures and 0 successes for this piece
        kind this run — conservatively demoted below untried ladder
        entries (never promoted above)."""
        out = set()
        for strat, (w, l) in self.kind_stats.get(kind, {}).items():
            if w == 0 and l >= 2:
                out.add(strat)
        return out

    def snapshot(self) -> dict:
        return {"kind_stats": self.kind_stats,
                "tokens_spent": self.tokens_spent,
                "accepts": self.n_accepts, "pieces": self.n_pieces}


class BudgetPolicy:
    """Deterministic conservative controller for one piece."""

    def __init__(self, piece, *, token_budget: int = 3600,
                 state: PolicyState | None = None):
        self.piece = piece
        self.budget = token_budget
        self.state = state or PolicyState()
        self.attempt = 0
        self.repairs = 0
        self.last_closeness = -1
        self.flat_streak = 0
        self.seen_candidates: set[str] = set()
        self.last_signature: tuple | None = None
        self.same_sig = 0
        self.log: list[Decision] = []

    # ------------------------------------------------------------ API
    def next_action(self, *, near_empty: bool = False,
                    structural_pass: bool = False,
                    failing_clauses: list[str] | None = None,
                    probe_pass: bool | None = None,
                    candidate_sha: str = "") -> Decision:
        clauses = failing_clauses or []
        closeness = self._closeness(clauses)

        # ---- dedup (never rescore an identical candidate)
        if candidate_sha and candidate_sha in self.seen_candidates:
            self.log.append(Decision(
                self.attempt, "stop", "duplicate candidate (semantic "
                "dedup) — resample with a new seed instead"))
            return self.log[-1]

        # ---- stop rules
        if self.state.tokens_spent + self._est_cost() > self.budget and \
                self.attempt >= 1:
            return self._stop("token budget nearly exhausted")
        if self.same_sig >= MAX_SAME_SIGNATURE:
            return self._stop(f"failure signature unchanged after "
                              f"{MAX_SAME_SIGNATURE} attempts")
        if self.flat_streak >= MAX_FLAT_CLOSNESS and self.repairs >= \
                MAX_MICRO_REPAIRS:
            return self._stop("closeness flat with repair budget spent")

        # ---- accept
        if structural_pass and probe_pass is not False and probe_pass is not None:
            self.log.append(Decision(
                self.attempt, "accept", "structural + behavioral pass"))
            return self.log[-1]
        if structural_pass and probe_pass is None:
            # no probe declared for this piece: structural acceptance
            self.log.append(Decision(
                self.attempt, "accept", "structural pass (no probe "
                "declared)"))
            return self.log[-1]

        # ---- behavioral failure on structurally-valid code => repair
        if structural_pass and probe_pass is False:
            if self.repairs < MAX_MICRO_REPAIRS:
                self.repairs += 1
                return self._act("micro_repair",
                                 "behavioral counterexample available",
                                 cost=140)
            return self._stop("behavioral repair budget exhausted")

        # ---- early-EOS handling (Phase-1 H5)
        if near_empty and self.attempt <= 1:
            return self._act("forced_continuation",
                             "near-empty candidate (early-EOS) — retry "
                             "with in-construct anchor", cost=self._est_cost())

        # ---- near-miss => micro-repair
        if 0 < len(clauses) <= NEAR_MISS_CLAUSES:
            if self.repairs < MAX_MICRO_REPAIRS:
                self.repairs += 1
                return self._act(
                    "micro_repair",
                    f"near-miss: {len(clauses)} failing clause(s) — "
                    f"bounded FIM repair", cost=140)
            # repairs spent: fall through to ladder

        # ---- ladder
        ladder = [s for s in LADDERS.get(self.piece.kind,
                                         ["exact_shape"])
                  if s not in self.state.demoted(self.piece.kind)]
        if not ladder:
            return self._stop("all ladder strategies demoted this run")
        idx = min(self.attempt, len(ladder) - 1)
        strat = ladder[idx]
        if strat == "decompose" and self.piece.kind not in (
                "route-handler", "invariant", "page", "prisma-model"):
            strat = "exact_shape_feedback"
        return self._act(strat, f"ladder index {idx} "
                         f"(kind={self.piece.kind})", cost=self._est_cost())

    def observe(self, *, action: str, candidate_sha: str,
                failing_clauses: list[str], tokens: int,
                success: bool = False, near_empty: bool = False) -> None:
        self.attempt += 1
        if candidate_sha:
            self.seen_candidates.add(candidate_sha)
        sig = tuple(sorted(failing_clauses[:3]))
        if sig == self.last_signature and sig:
            self.same_sig += 1
        else:
            self.same_sig = 0
            self.last_signature = sig
        closeness = self._closeness(failing_clauses)
        if closeness <= self.last_closeness:
            self.flat_streak += 1
        else:
            self.flat_streak = 0
        self.last_closeness = closeness
        self.state.record(self.piece.kind, action, success, tokens)
        if success:
            self.state.n_pieces += 1

    # ---------------------------------------------------------- helpers
    def _closeness(self, failing: list[str]) -> int:
        total = self._total_clauses()
        return max(0, total - len(failing))

    def _total_clauses(self) -> int:
        g = self.piece.gate
        return sum(len(g.get(k, [])) for k in
                   ("handlers", "calls", "accesses", "exprs", "uiStrings",
                    "exports")) + sum(
            len(m.get("fields", [])) for m in g.get("models", [])) + sum(
            len(i.get("members", {})) for i in g.get("interfaces", []))

    def _est_cost(self) -> int:
        return 450  # whole-construct generation estimate

    def _act(self, action: str, reason: str, cost: int) -> Decision:
        d = Decision(self.attempt, action, reason, strategy=action,
                     est_cost_tokens=cost)
        self.log.append(d)
        return d

    def _stop(self, reason: str) -> Decision:
        d = Decision(self.attempt, "stop", reason)
        self.log.append(d)
        return d
