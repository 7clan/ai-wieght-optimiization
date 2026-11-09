"""SESSION 037 — PHASE 5: reflective prompt evolution (lightweight).

A bounded GEPA/Reflexion adaptation for a 0.5B model on CPU:

  * A small set of INSTRUCTION SLOTS (plan, codegen, repair, checklist,
    context-selection, decomposition) each holds at most a few VARIANTS.
  * Variants are evaluated on DEV tasks only; the Pareto frontier over
    (resolved-rate, -tokens, -attempts, -teacher-intervention) is kept.
  * The frontier is re-checked on HELD-OUT tasks before a variant
    becomes the default; a variant that only helps dev tasks stays
    experimental.
  * Periodic compression: the longest active variant is rewritten
    shorter; if metrics do not degrade it replaces the long form
    (no unbounded prompt growth).
  * Every mutation is ledgered; rollback = reactivating the previous
    default.

Reflection signal: after each resolved-with-repair piece, the failure
clauses feed `archagent.generalize.principles.reflect_principle`; the
rule text can seed a new checklist variant (model-origin, marked).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

POOL_DEFAULT = Path(__file__).resolve().parents[2] / \
    "experiments" / "z037-generalization" / "promptevol" / "pool.json"

SLOTS = ("codegen_opening", "repair_instruction", "checklist",
         "context_selection")

# Seed variants: the exact wording that produced the Phase-2 smoke win,
# plus one principled alternative per slot (deterministic mutations).
SEED_VARIANTS: dict[str, list[dict]] = {
    "codegen_opening": [
        {"text": "Adapt the example's PATTERNS to this task's names — "
                 "never copy its domain words.",
         "origin": "session-036-exact-shape-law"},
        {"text": "Rewrite the example for this task: same structure, "
                 "different domain, every required element present.",
         "origin": "mutation-m1"},
    ],
    "repair_instruction": [
        {"text": "Write the missing logic; do not remove existing logic.",
         "origin": "baseline"},
        {"text": "Add ONLY the missing logic. Keep every existing line. "
                 "Match the surrounding code style.",
         "origin": "mutation-r1"},
    ],
    "checklist": [
        {"text": "", "origin": "none"},
        {"text": "Before finishing, check: every required element is "
                 "present; boundary cases behave as specified; no domain "
                 "words from the example remain.",
         "origin": "mutation-c1"},
    ],
    "context_selection": [
        {"text": "", "origin": "none"},
        {"text": "Use only the interfaces shown; do not invent fields.",
         "origin": "mutation-x1"},
    ],
}


@dataclass
class Variant:
    slot: str
    vid: str
    text: str
    origin: str
    status: str = "experimental"     # experimental|default|retired
    metrics: dict = field(default_factory=dict)
    # {dev_resolved, dev_total, dev_tokens, dev_attempts,
    #  heldout_resolved, heldout_total}
    history: list[str] = field(default_factory=list)


class PromptEvolution:
    def __init__(self, pool_path: Path = POOL_DEFAULT):
        self.pool_path = pool_path
        self.pool_path.parent.mkdir(parents=True, exist_ok=True)
        self.variants: list[Variant] = []
        self._load()

    # ------------------------------------------------------------- pool
    def _load(self) -> None:
        if self.pool_path.exists():
            for d in json.loads(self.pool_path.read_text()):
                self.variants.append(Variant(**d))
        else:
            for slot, seeds in SEED_VARIANTS.items():
                for i, s in enumerate(seeds):
                    v = Variant(slot=slot, vid=f"{slot[:3]}-{i+1}",
                                text=s["text"], origin=s["origin"])
                    if i == 0:
                        v.status = "default"
                    self.variants.append(v)
            self._save()

    def _save(self) -> None:
        self.pool_path.write_text(json.dumps(
            [asdict(v) for v in self.variants], indent=1))

    # ---------------------------------------------------------- access
    def active_text(self, slot: str) -> str:
        vs = [v for v in self.variants
              if v.slot == slot and v.status == "default"]
        return vs[0].text if vs else ""

    def experimental(self, slot: str) -> list[Variant]:
        return [v for v in self.variants
                if v.slot == slot and v.status == "experimental"]

    # ------------------------------------------------------- evolution
    def record(self, slot: str, vid: str, *, resolved: bool, tokens: int,
               attempts: int, split: str = "dev") -> None:
        for v in self.variants:
            if v.slot == slot and v.vid == vid:
                m = v.metrics
                m[f"{split}_resolved"] = m.get(f"{split}_resolved", 0) + \
                    int(resolved)
                m[f"{split}_total"] = m.get(f"{split}_total", 0) + 1
                m[f"{split}_tokens"] = m.get(f"{split}_tokens", 0) + tokens
                m[f"{split}_attempts"] = m.get(f"{split}_attempts", 0) + \
                    attempts
                self._save()
                return

    def pareto_frontier(self, slot: str, split: str = "dev") -> list[Variant]:
        """Non-dominated variants over (resolved-rate, -tokens/resolve,
        -attempts/resolve).  Teacher intervention is zero by design in
        zero-teacher tracks; recorded when nonzero."""
        vs = [v for v in self.variants
              if v.slot == slot and v.metrics.get(f"{split}_total", 0) >= 2]
        if not vs:
            return []

        def key(v):
            m = v.metrics
            tot = max(m.get(f"{split}_total", 1), 1)
            res = max(m.get(f"{split}_resolved", 0), 1e-9)
            return (m.get(f"{split}_resolved", 0) / tot,
                    -(m.get(f"{split}_tokens", 0) / res),
                    -(m.get(f"{split}_attempts", 0) / res))

        front = []
        for v in vs:
            kv = key(v)
            dominated = any(
                all(kw >= kv[i] for i, kw in enumerate(key(w)))
                and any(kw > kv[i] for i, kw in enumerate(key(w)))
                for w in vs if w is not v)
            if not dominated:
                front.append(v)
        return front

    def consider_promotion(self, slot: str) -> tuple[str, str]:
        """Promote an experimental variant to default only if it is on
        the DEV frontier AND does not regress the HELD-OUT check."""
        cur = [v for v in self.variants
               if v.slot == slot and v.status == "default"]
        exp_front = [v for v in self.pareto_frontier(slot)
                     if v.status == "experimental"]
        if not exp_front:
            return "keep", "no experimental variant on the dev frontier"
        cand = exp_front[0]
        cur_rate = _rate(cur[0], "heldout") if cur else (0, 0)
        cand_rate = _rate(cand, "heldout")
        if cand.metrics.get("heldout_total", 0) < 2:
            return "keep", (f"{cand.vid} on dev frontier but held-out "
                            f"sample < 2 — not promoted")
        if cand_rate[0] < cur_rate[0]:
            return "keep", (f"{cand.vid} regresses held-out "
                            f"({cand_rate[0]:.2f} < {cur_rate[0]:.2f})")
        if cur:
            cur[0].status = "retired"
            cur[0].history.append(
                f"{time.strftime('%F %T')} retired by {cand.vid}")
        cand.status = "default"
        cand.history.append(
            f"{time.strftime('%F %T')} promoted (dev frontier + held-out "
            f"non-regression)")
        self._save()
        return "promoted", f"{cand.vid} is the new default for {slot}"

    def compress_longest(self, slot: str) -> tuple[str, str]:
        """Periodic simplification: halve the longest active text; the
        compressed form is added as experimental (must re-earn its
        place).  Never silently replaces the default."""
        vs = [v for v in self.variants
              if v.slot == slot and v.status in ("default", "experimental")
              and len(v.text) > 160]
        if not vs:
            return "none", f"no long variant in {slot}"
        v = max(vs, key=lambda x: len(x.text))
        words = v.text.split()
        short = " ".join(words[: max(8, len(words) // 2)])
        nv = Variant(slot=slot, vid=f"{v.vid}c", text=short,
                     origin=f"compression-of-{v.vid}")
        nv.history.append(f"{time.strftime('%F %T')} compressed from "
                          f"{len(v.text)} to {len(short)} chars")
        self.variants.append(nv)
        self._save()
        return nv.vid, f"compressed {v.vid} -> {nv.vid} (experimental)"

    def add_variant(self, slot: str, text: str, origin: str) -> Variant:
        n = 1 + sum(1 for v in self.variants if v.slot == slot)
        v = Variant(slot=slot, vid=f"{slot[:3]}-m{n}", text=text,
                    origin=origin)
        self.variants.append(v)
        self._save()
        return v

    def snapshot(self) -> dict:
        return {v.slot: {"vid": v.vid, "status": v.status,
                         "len": len(v.text), "metrics": v.metrics}
                for v in self.variants if v.status != "retired"}


def _rate(v: Variant, split: str) -> tuple[float, int]:
    tot = v.metrics.get(f"{split}_total", 0)
    return (v.metrics.get(f"{split}_resolved", 0) / tot if tot else 0.0,
            tot)
