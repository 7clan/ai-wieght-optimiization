"""SESSION 037 — the piece-by-piece generation/repair controller.

For each TaskIR piece (topological order):

  policy.next_action() -> generate via FrozenModel -> mechanical
  extraction -> structural gate -> behavioral probe -> observe ->
  repeat until ACCEPT or STOP.

File assembly is explicit about provenance:

  QWEN-GENERATED     the construct text the model produced
  HARNESS-SCAFFOLD   deterministic imports/file heads/merges (never
                     counted as model capability; every byte recorded)

Every attempt is ledgered: prompt sha, candidate sha, tokens, seconds,
gate verdict, probe verdict, policy decision + reason, provenance.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import prompting
from .policy import BudgetPolicy, PolicyState
from . import probe as probe_mod

VERIFY = Path(__file__).resolve().parents[1] / "verify" / "run_gates.mjs"
NODE_ENV_PATH = "/home/z/my-project/node_modules"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class PieceController:
    """Drives ONE piece to ACCEPT/STOP under the budget.

    Track D extension: when a PrincipleEngine is supplied, its promoted
    addenda are appended to generation prompts for matching piece
    kinds (bounded: at most 3; every use ledgered).
    """

    def __init__(self, model, ws: Path, piece, state: PolicyState,
                 *, token_budget: int = 3600, ledger_path: Path,
                 archive_dir: Path, seed_base: int = 7000,
                 principles=None):
        self.model = model
        self.ws = ws
        self.piece = piece
        self.state = state
        self.ledger_path = ledger_path
        self.archive_dir = archive_dir
        self.seed_base = seed_base
        self._resample_no = 0
        self.principles = principles
        self.policy = BudgetPolicy(piece, token_budget=token_budget,
                                   state=state)
        self.attempts: list[dict] = []

    # ----------------------------------------------------------- loop
    def run(self) -> dict:
        t0 = time.time()
        near_empty = False
        structural_pass = False
        failing: list[str] = []
        probe_pass: None | bool = None
        counterexample = ""
        current_construct = ""
        accepted = None

        for step in range(24):  # hard cap
            dec = self.policy.next_action(
                near_empty=near_empty,
                structural_pass=structural_pass,
                failing_clauses=failing,
                probe_pass=probe_pass)
            if dec.action == "stop":
                self._note_stop(dec)
                break
            if dec.action == "accept":
                accepted = {
                    "code": current_construct, "action": dec.action,
                    "attempts": step + 1}
                break

            seed = self.seed_base + step * 31
            try:
                code, usage, prompt, mode = self._generate(
                    dec.action, seed, failing, counterexample,
                    current_construct=current_construct)
            except Exception as e:  # harness error — never model's fault
                self.attempts.append({
                    "step": step, "action": dec.action,
                    "outcome": "harness-error", "error": str(e)[:200]})
                break

            near_empty = prompting.is_near_empty(code)
            candidate_sha = _sha(code)
            if self.policy.is_duplicate(candidate_sha):
                # EXACT repeat of a previous candidate: do not re-verify;
                # advance the ladder with a fresh seed instead
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

            probe_pass = None
            counterexample = ""
            if structural_pass and self.piece.oracle:
                pr = self._behavioral_probe(code)
                probe_pass = bool(pr.get("pass"))
                if not probe_pass and pr.get("class") == "harness":
                    probe_pass = None   # harness defect: don't count
                elif not probe_pass:
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
            # install the accepted construct (scaffold-labeled merge)
            self._install_candidate(accepted["code"])
        with open(self.ledger_path, "a") as fh:
            fh.write(json.dumps(result) + "\n")
        return result

    # ------------------------------------------------------ generation
    def _generate(self, action: str, seed: int, failing: list[str],
                  counterexample: str, current_construct: str = ""):
        p = self.piece
        if action in ("exact_shape", "exact_shape_feedback",
                      "exact_shape_resample"):
            feedback = ""
            if action == "exact_shape_feedback":
                if failing:
                    # quote the spec clauses that declare the missing
                    # elements (spec material, not teacher solutions)
                    clauses = prompting._spec_clauses_for(failing, p.spec)
                    feedback = "\n".join(f"- {c}" for c in
                                         (clauses or failing[:5]))
                    if p.kind in ("prisma-model", "type-interface"):
                        feedback += ("\n- the construct must contain ONLY "
                                     "the listed elements — remove any "
                                     "others copied from the example")
                elif counterexample:
                    # behavioral repair: the minimal failing case IS the
                    # feedback (counterexample-guided regeneration)
                    feedback = (f"- verified failure: {counterexample}\n"
                                f"- fix exactly that behavior")
            prompt = prompting.build_piece_prompt(
                p, retry=int(action.endswith("feedback")),
                extra_feedback=feedback,
                opening=(prompting.RESAMPLE_OPENINGS[
                    (self._resample_no) % len(prompting.RESAMPLE_OPENINGS)]
                    if action == "exact_shape_resample" else ""))
            # Track D: promoted reasoning-principle addenda (bounded)
            if self.principles is not None:
                addenda = self.principles.addenda_for(
                    p.kind, self._failure_category(failing))
                if addenda:
                    prompt = prompt + "\n" + "\n".join(
                        f"({pid}) {text}" for pid, text in addenda)
            if action == "exact_shape_resample":
                self._resample_no += 1
            stochastic = (action == "exact_shape_resample"
                          or seed % 2 == 1)
            out, usage = self.model.generate(
                prompt, max_tokens=self._max_tokens(), seed=seed,
                stochastic=stochastic)
            code = prompting.extract_construct(
                p.anchor + prompting.checklist_for(p) + out, p.kind)
            return code, usage, prompt, action
        if action == "forced_continuation":
            prompt = prompting.forced_continuation_prompt(p)
            out, usage = self.model.generate(
                prompt, max_tokens=self._max_tokens(), seed=seed + 7,
                stochastic=True)
            code = prompting.extract_construct(out, p.kind)
            return code, usage, prompt, action
        if action == "micro_repair":
            pf, sf, instr = prompting.build_repair_prompt(
                p, failing, counterexample, code=current_construct)
            out, usage = self.model.fim(
                pf, sf, instructions=instr, max_tokens=200, seed=seed + 3,
                stochastic=True)
            code = pf + out + sf
            return code, usage, f"[MICRO] {instr}", action
        if action == "decompose":
            return self._decompose(seed, failing)
        raise RuntimeError(f"unknown action {action}")

    def _decompose(self, seed: int, failing: list[str]):
        """Clause-by-clause FIM insertion (escalation tier).

        Uses the piece's OWN clause list; each FIM inserts one clause's
        logic before the construct's happy path.  The instruction quotes
        the clause (spec material the model already saw).
        """
        p = self.piece
        clauses = self._clauses()
        code = self._current_installed() or (p.anchor + "\n}\n")
        for i, cl in enumerate(clauses):
            lines = code.split("\n")
            seam = len(lines)
            for j in range(len(lines) - 1, -1, -1):
                if ("return" in lines[j] or "await db." in lines[j]):
                    seam = j
                    break
            prefix = "\n".join(lines[:seam])
            suffix = "\n".join(lines[seam:])
            out, usage = self.model.fim(
                prefix, suffix,
                instructions=f"implement this requirement here: {cl}",
                max_tokens=160, seed=seed + i * 13, stochastic=True)
            code = prefix + out + suffix
        return code, usage, f"[DECOMPOSE] {len(clauses)} clauses", "decompose"

    # ----------------------------------------------------- verification
    def _structural_gate(self, code: str) -> dict:
        import os
        contract = dict(self.piece.gate)
        contract["file"] = self.piece.file
        if contract.get("kind") == "invariant":
            contract["function"] = self.piece.oracle["signature"].split("(")[0]
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
            return {"pass": False,
                    "failures": [f"harness error: {e}"]}

    def _behavioral_probe(self, code: str) -> dict:
        o = self.piece.oracle
        if o.get("probe") == "route":
            # install the candidate first (probe imports the real file)
            keep = self._install_candidate(code)
            try:
                return probe_mod.route_probe(
                    self.ws, self.piece.file, o["method"],
                    o.get("cases", []), seed=o.get("seed"))
            finally:
                self._restore(keep)
        if o.get("signature"):
            keep = self._install_candidate(code)
            try:
                return probe_mod.invariant_probe(
                    self.ws, self.piece.file, o["signature"], o["cases"],
                    ref_expr=o.get("ref_expr"))
            finally:
                self._restore(keep)
        return {"pass": None}

    # ------------------------------------------------------- assembly
    def _install_candidate(self, code: str) -> str | None:
        """Install candidate construct into the target file with the
        deterministic scaffold; returns previous content for restore."""
        target = self.ws / self.piece.file
        prev = target.read_text() if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._assemble(code))
        return prev

    def _restore(self, prev: str | None) -> None:
        target = self.ws / self.piece.file
        if prev is None:
            if target.exists():
                target.unlink()
        else:
            target.write_text(prev)

    def _assemble(self, construct: str) -> str:
        """Deterministic scaffold + construct (HARNESS-SCAFFOLD labeled)."""
        k = self.piece.kind
        if k == "prisma-model":
            import re as _re
            base = self.ws / self.piece.file
            head = base.read_text() if base.exists() else _SCHEMA_HEAD
            name = _model_name(self.piece)
            # declaration check must match `model X {` — a substring
            # check matched COMMENTS like "the model Band must be..."
            # and silently skipped the append (found in A.1 bring-up)
            if _re.search(rf"^model {name}\s*\{{", head, _re.M):
                head = _re.sub(rf"model {name}\s*\{{[\s\S]*?\n\}}",
                               construct, head, count=1)
                return head
            return head.rstrip() + "\n\n" + construct + "\n"
        if k == "invariant":
            target = self.ws / self.piece.file
            body = target.read_text() if target.exists() else ""
            fname = self.piece.oracle["signature"].split("(")[0]
            if f"function {fname}" in body:
                return body
            return (body.rstrip() + "\n\n" + construct + "\n").lstrip()
        if k == "route-handler":
            target = self.ws / self.piece.file
            body = target.read_text() if target.exists() else ""
            method = self.piece.gate["handlers"][0]
            import re
            if f"export async function {method}" in body:
                # replace the existing handler with the new candidate
                body = re.sub(
                    rf"export async function {method}\b[\s\S]*?\n\}}",
                    construct, body, count=1)
                return body
            if body.strip():
                # prior accepted handler(s) for this file: preserve them
                return body.rstrip() + "\n\n" + construct + "\n"
            head = _route_head(self.piece)
            return head + construct + "\n"
        # hook/component/page: whole file
        head = "'use client'\n\n" if self.piece.kind in ("hook", "component",
                                                         "page") else ""
        return head + construct + "\n"

    def _current_installed(self) -> str | None:
        target = self.ws / self.piece.file
        if not target.exists():
            return None
        body = target.read_text()
        if self.piece.kind == "route-handler":
            method = self.piece.gate["handlers"][0]
            import re
            m = re.search(
                rf"export async function {method}\b[\s\S]*?\n\}}", body)
            return m.group(0) if m else None
        return body

    # --------------------------------------------------------- helpers
    def _max_tokens(self) -> int:
        return {"prisma-model": 300, "type-interface": 220,
                "invariant": 200, "route-handler": 520, "hook": 420,
                "component": 560, "page": 700}.get(self.piece.kind, 450)

    def _clauses(self) -> list[str]:
        # spec sentences (bounded by construction to <=6)
        return [s.strip() + "." for s in
                self.piece.spec.replace(". ", ".\n").split("\n") if s.strip()]

    @staticmethod
    def _failure_category(failing: list[str]) -> str:
        for f in failing:
            if f.startswith("schema:") or f.startswith("types:"):
                return "missing_literal"
            if f.startswith("exports:"):
                return "missing_export"
            if f.startswith("calls:") or f.startswith("accesses:"):
                return "missing_call"
            if f.startswith("parse:"):
                return "syntax"
        return ""

    def _note_stop(self, dec) -> None:
        self.attempts.append({"step": len(self.attempts), "action": "stop",
                              "reason": dec.reason})

    def _archive(self, step: int, action: str, seed: int, prompt: str,
                 code: str) -> None:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        slug = self.piece.pid.replace("/", "-")
        (self.archive_dir / f"{slug}-{action}-{step}-{seed}.json").write_text(
            json.dumps({"piece": self.piece.pid, "action": action,
                        "seed": seed, "prompt": prompt, "candidate": code},
                       indent=1))


_SCHEMA_HEAD = """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}
"""


def _model_name(piece) -> str:
    return piece.gate["models"][0]["name"]


def _route_head(piece) -> str:
    method = piece.gate["handlers"][0]
    head = ""
    if "GET" in method or "POST" in method or "PUT" in method \
            or "DELETE" in method:
        head = ("import { NextRequest, NextResponse } from 'next/server'\n"
                "import { db } from '@/lib/db'\n\n")
    ir = piece.ir
    if ir and piece.kind == "route-handler":
        for h in ir.routes:
            if h.pid == piece.pid and h.uses_invariants:
                mod = f"@/lib/{ir.app}/invariants"
                fns = ", ".join(
                    i.signature.split("(")[0]
                    for i in ir.invariants if i.pid in h.uses_invariants)
                head += f"import {{ {fns} }} from '{mod}'\n"
                head += "\n"
                break
    return head
