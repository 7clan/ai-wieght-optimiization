"""SESSION 037 — PHASE 4: the reusable reasoning-principle engine.

A principle is a compact, GENERALIZED procedural rule — never a copied
solution.  Principles are born from (verified failure, verified
correction) pairs, de-taskified, then must EARN promotion by improving
outcomes on DIFFERENT problems; a principle that works once is a
hypothesis, not learning.

Lifecycle:

  candidate   created after failure->correction (model-reflected or
              template-mined; origin recorded)
  validated   applied to >=2 different problems with A/B measurement
  promoted    only with >=1 improvement AND 0 regressions across the
              validation set
  demoted     a promoted principle that later regresses (rollback)
  rejected    no transfer, or merely reproduces seen answers

Principles act as prompt ADDENDA when their trigger matches (piece
kind + failure category).  They are part of Track D only; every use is
ledgered so attribution stays clean.

Storage: experiments/z037-generalization/principles/store.jsonl
(one JSON per line, append-only; versioned by (id, version)).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

STORE_DEFAULT = Path(__file__).resolve().parents[2] / \
    "experiments" / "z037-generalization" / "principles" / "store.jsonl"

TASK_TOKEN_RE = re.compile(
    r"\b(room|reservation|courier|parcel|approval|equipment|maintenance|"
    r"pricing|quota|stockpilot|roomreserve|taskflow|medivault|order|"
    r"invoice|ticket)\b", re.I)

CODE_SOLUTION_RE = re.compile(r"(=>|;\s*$|\bawait\b|\breturn\b.*\{|"
                              r"\bconst\b|\bfunction\b\s*\()")


@dataclass
class Evidence:
    task: str            # piece id of the validation task
    piece_kind: str
    without: str         # "resolved" | "failed" | "tokens:N"
    with_: str
    tokens_without: int = 0
    tokens_with: int = 0


@dataclass
class Principle:
    pid: str
    version: int
    origin: str                     # model-reflected | template-mined |
                                    # teacher-seeded
    error_pattern: str              # de-taskified failure description
    principle: str                  # the general rule
    prompt_addendum: str            # what gets injected into prompts
    trigger_kind: str               # piece kind it applies to
    trigger_category: str = ""      # failure category ("" = any)
    status: str = "candidate"       # candidate|validated|promoted|
                                    # demoted|rejected
    evidence: list[Evidence] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    created_at: str = ""
    promoted_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [asdict(e) for e in self.evidence]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Principle":
        ev = [Evidence(**e) for e in d.get("evidence", [])]
        return Principle(**{**d, "evidence": ev})


class PrincipleEngine:
    def __init__(self, store_path: Path = STORE_DEFAULT):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.principles: list[Principle] = []
        self._load()

    # ------------------------------------------------------------ store
    def _load(self) -> None:
        if not self.store_path.exists():
            return
        seen = set()
        for line in self.store_path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            key = (d["pid"], d["version"])
            if key in seen:      # last write wins
                self.principles = [p for p in self.principles
                                   if (p.pid, p.version) != key]
            seen.add(key)
            self.principles.append(Principle.from_dict(d))

    def _append(self, p: Principle) -> None:
        with open(self.store_path, "a") as fh:
            fh.write(json.dumps(p.to_dict()) + "\n")

    # ------------------------------------------------------- candidates
    def de_taskified(self, text: str) -> list[str]:
        """Mechanical de-taskification audit: report task-specific
        identifiers that must not appear in a general principle."""
        return sorted(set(m.group(0).lower()
                          for m in TASK_TOKEN_RE.finditer(text)))

    def propose(self, *, origin: str, error_pattern: str,
                principle: str, prompt_addendum: str, trigger_kind: str,
                trigger_category: str = "") -> tuple[Principle | None, str]:
        """Create a candidate principle (after failure->correction)."""
        # --- de-taskification (rule 3): reject task-soaked text
        leaks = self.de_taskified(error_pattern + " " + principle + " "
                                  + prompt_addendum)
        # --- not-a-solution check (rule 6): principles are prose, not code
        if CODE_SOLUTION_RE.search(prompt_addendum):
            return None, "rejected at proposal: addendum looks like code, " \
                         "not a procedural rule"
        n = 1 + sum(1 for p in self.principles if p.origin == origin)
        pid = f"PR-{origin.split('-')[0][:3].upper()}-{n:03d}"
        p = Principle(
            pid=pid, version=1, origin=origin,
            error_pattern=error_pattern, principle=principle,
            prompt_addendum=prompt_addendum, trigger_kind=trigger_kind,
            trigger_category=trigger_category, status="candidate",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        if leaks:
            p.failures.append(f"de-taskification leak at proposal: {leaks} "
                              f"(kept as candidate; leaks must be fixed "
                              f"before validation)")
        self.principles.append(p)
        self._append(p)
        return p, ("proposed with leak warning: " + str(leaks) if leaks
                   else "proposed")

    # ------------------------------------------------------ application
    def addenda_for(self, piece_kind: str, failure_category: str = "") \
            -> list[tuple[str, str]]:
        """Active addenda (promoted only, or explicitly included
        candidates during validation) for this trigger."""
        out = []
        for p in self.principles:
            if p.status not in ("promoted", "validating"):
                continue
            if p.trigger_kind and p.trigger_kind != piece_kind:
                continue
            if p.trigger_category and p.trigger_category and \
                    p.trigger_category != failure_category:
                continue
            out.append((p.pid, p.prompt_addendum))
        return out[:3]   # bounded: no unbounded prompt growth (Phase 5)

    # ------------------------------------------------------- promotion
    def record_evidence(self, pid: str, ev: Evidence) -> None:
        for p in self.principles:
            if p.pid == pid and p.status in ("candidate", "validating",
                                             "promoted"):
                p.evidence.append(ev)
                self._append(p)
                return
        raise KeyError(pid)

    def evaluate_promotion(self, pid: str,
                           min_tasks: int = 2) -> tuple[str, str]:
        """Apply the promotion rules.  Returns (new_status, reason)."""
        cands = [p for p in self.principles if p.pid == pid]
        if not cands:
            return "", "unknown principle"
        p = max(cands, key=lambda x: x.version)
        if p.de_taskification_pending():
            return p.status, "blocked: task-specific identifiers present"
        tasks = {e.task for e in p.evidence}
        if len(tasks) < min_tasks:
            return p.status, f"only {len(tasks)} validation task(s) " \
                             f"(need >= {min_tasks}) — hypothesis, not " \
                             f"learning"
        improved = 0
        regressed = 0
        for e in p.evidence:
            if e.without == "failed" and e.with_ == "resolved":
                improved += 1
            elif e.without == "resolved" and e.with_ == "failed":
                regressed += 1
        if regressed > 0:
            p.status = "rejected"
            p.failures.append(f"regression on {regressed} validation task(s)")
            self._append(p)
            return p.status, f"rejected: {regressed} regression(s)"
        if improved == 0:
            p.status = "rejected"
            p.failures.append("no improvement on any validation task — "
                              "merely reproduces existing behavior")
            self._append(p)
            return p.status, "rejected: no transfer"
        p.status = "promoted"
        p.promoted_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._append(p)
        return p.status, (f"promoted: {improved} improvement(s), 0 "
                          f"regressions across {len(tasks)} tasks")

    def rollback(self, pid: str, reason: str) -> str:
        """Demote a promoted principle (evidence-based rollback)."""
        cands = [p for p in self.principles if p.pid == pid]
        if not cands:
            return "unknown"
        p = max(cands, key=lambda x: x.version)
        if p.status != "promoted":
            return p.status
        p.version += 1
        p.status = "demoted"
        p.failures.append(f"rolled back: {reason}")
        self._append(p)
        return p.status

    # ---------------------------------------------------------- report
    def snapshot(self) -> dict:
        out: dict[str, list] = {"promoted": [], "candidate": [],
                                "rejected": [], "demoted": []}
        for p in self.principles:
            d = {"pid": p.pid, "v": p.version, "origin": p.origin,
                 "principle": p.principle[:120],
                 "trigger": f"{p.trigger_kind}/{p.trigger_category}",
                 "evidence": [(e.task, e.without, e.with_)
                              for e in p.evidence]}
            out.setdefault(p.status, []).append(d)
        return out


def _Principle_de_taskification_pending(self) -> bool:
    leaks = TASK_TOKEN_RE.findall(self.error_pattern + " " + self.principle
                                  + " " + self.prompt_addendum)
    return bool(leaks)


Principle.de_taskification_pending = _Principle_de_taskification_pending


# --------------------------------------------------- model reflection

PRINCIPLE_REFLECTION_PROMPT = """You wrote code for a task. An automated
verifier found this mistake:

{failure}

The corrected code now passes. State the GENERAL lesson: one short
procedural rule that would prevent this class of mistake in ANY
application. Do not mention the specific task, its names, or its data.
Format: RULE: <one sentence>"""


def reflect_principle(model, failure_description: str,
                      correction_summary: str, seed: int = 1234
                      ) -> tuple[str, str]:
    """Ask the frozen model to state the general rule (Phase 5's
    reflection loop feeds Phase 4).  Returns (rule, raw)."""
    prompt = PRINCIPLE_REFLECTION_PROMPT.format(
        failure=failure_description[:600])
    out, usage = model.generate(prompt, max_tokens=90, seed=seed,
                                stochastic=False)
    rule = out.strip()
    m = re.search(r"RULE:\s*(.+)", rule, re.S)
    if m:
        rule = m.group(1).strip().split("\n")[0]
    rule = rule[:220]
    return rule, out
