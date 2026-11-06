"""Autonomous development harness runner (mission sections 6-7).

Staged process for TaskFlow:
  Stage A  requirements -> architectural plan, scored vs reference
  Stage B/C  data model + storage  -> store module
  Stage D  API routes              -> api module (needs passing store)
  Stage E  React UI                -> ui + css modules
  Stage F  integration             -> real app assembled by scaffold

Per module: greedy baseline -> public evaluation -> bounded repair loop
(whole-module candidates + native FIM splices anchored at the failing
line) -> accept only strict improvements -> freeze -> holdout later.

Every attempt is recorded with seed, usage, checks and lineage; the
selected module's bytes always replay from recorded model completions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "zai-taskflow"
GEN = EXP / "generations"
REPORTS = EXP / "reports"
MEMORY = EXP / "repair_memory"
WORKER = str(Path(__file__).with_name("worker.js"))

from archagent import contracts, retrieval
from archagent.repair_memory import RepairMemory, record_repair  # noqa: E402

MAX_ROUNDS = 8
CANDIDATES_PER_ROUND = 5          # 1 greedy + 2 sampled + 2 FIM
WALL_BUDGET_ROLE = 45 * 60        # seconds per role
GEN_TOKENS = {"logic": 320, "store": 900, "api": 900, "ui": 1100,
              "css": 420, "stage_a": 420}

sys.path.insert(0, str(ROOT))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


# ---------------------------------------------------------------------------
# evaluation via the isolated worker
# ---------------------------------------------------------------------------

def public_cases(role: str):
    if role == "logic":
        return contracts.LOGIC_PUBLIC
    if role == "store":
        return contracts.STORE_SCENARIO_PUBLIC
    if role == "api":
        return contracts.API_CHECKS_PUBLIC
    return None


def holdout_cases(role: str):
    if role == "logic":
        return contracts.LOGIC_HOLDOUT
    if role == "store":
        return contracts.STORE_SCENARIO_HOLDOUT
    if role == "api":
        return contracts.API_CHECKS_HOLDOUT
    return None


def evaluate_module(role: str, source: str, *, store_source=None,
                    logic_source=None, phase="public", timeout=60) -> dict:
    cases = (public_cases(role) if phase == "public"
             else holdout_cases(role))
    payload = {
        "role": role, "source": source, "phase": phase,
        "cases": cases or [],
        "extra": {"storeSource": store_source, "logicSource": logic_source},
    }
    with tempfile.TemporaryDirectory(prefix="archagent-") as tmp:
        inp, outp = Path(tmp) / "in.json", Path(tmp) / "out.json"
        inp.write_text(json.dumps(payload), encoding="utf8")
        env = dict(os.environ)
        env.update({
            "ARCHAGENT_LOCAL_EVAL": "1",
            "NODE_PATH": os.environ.get("ARCHAGENT_NODE_PATH",
                                        "/home/z/my-project/evalenv/node_modules"),
            "NODE_ENV": "production",
        })
        try:
            proc = subprocess.run(["node", WORKER, str(inp), str(outp)],
                                  capture_output=True, text=True, timeout=timeout,
                                  check=False, env=env)
        except subprocess.TimeoutExpired:
            return {"passed": False, "syntax_valid": False, "checks": {},
                    "failures": [{"check": "timeout",
                                  "detail": f"worker exceeded {timeout}s"}],
                    "error": "timeout"}
        if proc.returncode or not outp.is_file():
            return {"passed": False, "syntax_valid": False, "checks": {},
                    "failures": [{"check": "crash",
                                  "detail": proc.stderr[-300:]}],
                    "error": proc.stderr[-200:] or "worker crashed"}
        return json.loads(outp.read_text(encoding="utf8"))


def score_of(result: dict) -> tuple[int, int]:
    checks = result.get("checks", {})
    return sum(1 for v in checks.values() if v), len(checks)


def first_failure(result: dict) -> dict | None:
    fails = result.get("failures", [])
    return fails[0] if fails else None


def failing_line(result: dict) -> int | None:
    err = result.get("error") or ""
    m = re.search(r"qwen-[a-z]+\.js:(\d+):(\d+)", err)
    if m:
        return int(m.group(1))
    for f in result.get("failures", []):
        m = re.search(r"@?line (\d+)", str(f.get("detail", "")))
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

def _prev_excerpt(source: str, result: dict, hide_full: bool) -> str:
    """The model's own previous bytes, commentized.  Early rounds show the
    full module; later rounds show head+tail+failing lines only (Session
    031's seventh amendment: break the copy-rut)."""
    lines = source.splitlines()
    anchor = failing_line(result)
    if not hide_full:
        shown = lines
    else:
        head = lines[:16]
        tail = lines[-8:]
        mid = []
        if anchor and 1 <= anchor <= len(lines):
            lo, hi = max(1, anchor - 3), min(len(lines), anchor + 3)
            mid = [f"{no}: {lines[no-1]}" for no in range(lo, hi + 1)]
        shown = head + ["... (middle lines omitted) ..."] + mid + tail
    role_guess = "store" if "createStore" in source else \
                 "api" if "createApi" in source else \
                 "ui" if "App" in source and "React" in source else "css"
    return contracts.commentize(role_guess, "\n".join(shown)[:4000], width=104)


_CONCEPTS = [
    (re.compile(r"Assignment to constant variable", re.I),
     "In JavaScript a const binding cannot be reassigned; use let for "
     "variables that must change."),
    (re.compile(r"ENOENT|no such file or directory", re.I),
     "Read the persistence file only when it exists; a fresh install "
     "starts with an empty state."),
    (re.compile(r"is not a function"), ""),
    (re.compile(r"Disallowed module"), ""),
    (re.compile(r"status -?1 \(want|status \d+ \(want \d+\)", re.I),
     "Every route must answer exactly once with the contract status code "
     "and JSON body."),
    (re.compile(r"threw Error", re.I),
     "Validate inputs and unknown ids as documented; throw in the store "
     "is expected, but the API must catch and answer 400/404."),
    (re.compile(r"offline", re.I),
     "When fetch rejects or res.ok is false, switch to offline demo mode "
     "and render the built-in demo data."),
]


def _concept_note(role: str, result: dict) -> str:
    blob = json.dumps(result.get("failures", [])) + (result.get("error") or "")
    for pattern, note in _CONCEPTS:
        if pattern.search(blob):
            return note or "Check the failing construct against the reference."
    return ""


# ---------------------------------------------------------------------------
# FIM repair (anchored at the failing line)
# ---------------------------------------------------------------------------

def fim_window(source: str, anchor: int, window: int = 14):
    lines = source.splitlines(keepends=True)
    lo = max(0, anchor - window // 2)
    hi = min(len(lines), lo + window)
    return "".join(lines[:lo]), "".join(lines[hi:]), lo


def fim_instructions(role: str, result: dict) -> str:
    f = first_failure(result)
    concept = _concept_note(role, result)
    detail = f.get("detail", "") if f else ""
    return ("\n// FIX the region below. Failure: " + str(f.get("check") if f else "")
            + " " + detail[:160].replace("\n", " ")
            + (("\n// Concept: " + concept) if concept else "")
            + "\n// Keep everything else identical.\n")


def splice(source: str, fill: str, lo: int, hi: int) -> str:
    lines = source.splitlines(keepends=True)
    new_fill = fill if fill.endswith("\n") or not fill else fill + "\n"
    return "".join(lines[:lo]) + new_fill + "".join(lines[hi:])


# ---------------------------------------------------------------------------
# generation loop
# ---------------------------------------------------------------------------

class Harness:
    def __init__(self, model, docs: bool = False, memory: RepairMemory | None = None):
        self.model = model
        self.docs = docs
        self.memory = memory
        self.log = GEN / ("generations_docs.jsonl" if docs else "generations.jsonl")
        GEN.mkdir(parents=True, exist_ok=True)

    def record(self, entry: dict) -> None:
        with open(self.log, "a", encoding="utf8") as f:
            f.write(json.dumps(entry) + "\n")

    def develop(self, role: str, *, store_source=None, logic_source=None,
                max_rounds=MAX_ROUNDS, wall=WALL_BUDGET_ROLE) -> dict:
        t0 = time.time()
        best = {"source": None, "result": None, "score": (-1, -1),
                "attempt_id": None}
        attempts = []
        round_i = 0
        stopped = None
        while True:
            if round_i > max_rounds:
                stopped = "rounds"; break
            if time.time() - t0 > wall:
                stopped = "wall"; break
            candidates = []
            if round_i == 0:
                prompt = contracts.prompt(
                    role, docs=retrieval.doc_block(role) if self.docs else "")
                candidates.append(("whole-greedy", prompt, 1, False))
            else:
                prev, res = best["source"], best["result"]
                feedback = "; ".join(
                    f"{f.get('check')}: {f.get('detail', '')}"
                    for f in res.get("failures", [])[:4])[:600]
                mem_block = (self.memory.prompt_block(role, feedback)
                             if self.memory else "")
                hide_full = round_i >= 3  # seventh-amendment copy-rut break
                rp = contracts.prompt(
                    role,
                    docs=retrieval.doc_block(role) if self.docs else "",
                    feedback=feedback,
                    previous_excerpt=_prev_excerpt(prev, res, hide_full),
                    self_note=mem_block.rstrip() if mem_block else "")
                candidates.append(("whole-greedy", rp, round_i * 1000, False))
                for k in range(2):
                    candidates.append(("whole-sample", rp,
                                       round_i * 1000 + 10 + k, True))
                anchor = failing_line(res)
                if anchor:
                    prefix, suffix, lo = fim_window(prev, anchor)
                    instr = fim_instructions(role, res)
                    for k in range(2):
                        candidates.append(("fim", (prefix, suffix, instr),
                                           round_i * 1000 + 20 + k, k > 0,
                                           (lo, lo + 14)))
            improved = False
            for cand in candidates:
                if time.time() - t0 > wall:
                    stopped = "wall"; break
                kind = cand[0]
                if kind == "fim":
                    _, (prefix, suffix, instr), seed, stoch, (lo, hi) = cand
                    fill, usage = self.model.fim(
                        prefix, suffix, instructions=instr,
                        max_tokens=320, seed=seed, stochastic=stoch)
                    if _degenerate(fill):
                        fill, usage = self.model.fim(
                            prefix, suffix, instructions=instr,
                            max_tokens=320, seed=seed + 500, stochastic=True)
                    source = splice(best["source"], fill, lo, hi)
                    origin = {"type": "fim", "base_sha256": sha(best["source"]),
                              "fill": fill[:2000], "anchor_line": lo + 1,
                              "seed": seed}
                else:
                    _, prompt, seed, stoch = cand
                    completion, usage = self.model.generate(
                        prompt, max_tokens=GEN_TOKENS[role], seed=seed,
                        stochastic=stoch)
                    if _degenerate(completion):
                        completion, usage = self.model.generate(
                            prompt, max_tokens=GEN_TOKENS[role],
                            seed=seed + 500, stochastic=True)
                    source = _post_process(role, completion)
                    origin = {"type": "whole", "seed": seed}
                result = evaluate_module(role, source,
                                         store_source=store_source,
                                         logic_source=logic_source)
                sc = score_of(result)
                attempt_id = f"{role}-r{round_i}-{kind}-{seed}"
                entry = {
                    "id": attempt_id, "role": role, "round": round_i,
                    "kind": kind, "seed": seed, "stochastic": stoch,
                    "usage": usage, "checks_passed": sc[0],
                    "checks_total": sc[1],
                    "syntax_valid": result.get("syntax_valid"),
                    "accepted": False, "origin": origin,
                    "source_sha256": sha(source), "source": source,
                    "failures": result.get("failures", [])[:8],
                    "error": result.get("error"),
                }
                self.record(entry)
                attempts.append(attempt_id)
                if sc > best["score"]:
                    if best["source"] is not None and self.memory is not None:
                        rec = record_repair(
                            role=role,
                            requirement=contracts.GOALS[role][:400],
                            failed_source=best["source"],
                            failure_detail=json.dumps(
                                best["result"].get("failures", [])[:2]),
                            repaired_source=source,
                            corrected_behavior=f"checks {sc[0]}/{sc[1]}",
                            anchor_line=failing_line(best["result"]),
                            contract_refs=[f"{role}:public"])
                        self.memory.add(rec)
                    best = {"source": source, "result": result, "score": sc,
                            "attempt_id": attempt_id}
                    improved = True
                    print(f"  [{role}] r{round_i} {kind} -> {sc[0]}/{sc[1]}",
                          flush=True)
                if sc[1] and sc[0] == sc[1]:
                    break
            if best["score"][1] and best["score"][0] == best["score"][1]:
                stopped = "pass"; break
            if not improved and round_i > 0 and round_i >= 3 and \
                    best["score"][0] == 0:
                stopped = "plateau-zero"; break
            round_i += 1
        return {"role": role, "best": best, "attempts": attempts,
                "stopped": stopped, "wall": round(time.time() - t0, 1),
                "usage": self.model.usage()}


def _post_process(role: str, completion: str) -> str:
    """Deterministic anchor+cleanup: module = anchor + cleaned completion.

    Only strips code fences and trailing prose around the model's own
    bytes; never adds, fixes or rewrites model code.  The anchor is the
    public-contract signature (TRUSTED-SCAFFOLD, disclosed)."""
    text = completion
    m = re.search(r"```(?:python|jsx|javascript|js|css)?\s*\n(.*?)```",
                  text, re.S)
    if m and len(m.group(1)) > 40:
        text = m.group(1)
    if role == "logic":
        keep = []
        for line in text.splitlines():
            if line and not line[0].isspace() and keep and \
                    not line.startswith(("def ", "return", ")", "}")):
                break
            keep.append(line)
        text = "\n".join(keep)
        return contracts.ANCHOR[role] + text.rstrip() + "\n"
    if role == "css":
        if "`" in text:
            text = text[:text.index("`") + 1]
        else:
            text = text.rstrip() + "\n`"
        return contracts.ANCHOR[role] + text.lstrip("\n") + \
            "\nmodule.exports = css;\n"
    last = max(text.rfind("}"), 0)
    if last:
        text = text[:last + 1]
    return contracts.ANCHOR[role] + text.strip() + "\n"


def _degenerate(text: str) -> bool:
    """Detect greedy repetition loops (>40% identical non-empty lines)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 6:
        return False
    from collections import Counter
    counts = Counter(lines)
    return counts.most_common(1)[0][1] / len(lines) > 0.4


# ---------------------------------------------------------------------------
# stage A scoring
# ---------------------------------------------------------------------------

def score_stage_a(plan_text: str) -> dict:
    m = re.search(r"\{.*\}", plan_text, re.S)
    if not m:
        return {"valid_json": False, "scores": {}, "raw": plan_text[:300]}
    try:
        plan = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"valid_json": False, "scores": {}, "raw": plan_text[:300]}
    ref = contracts.STAGE_A_REFERENCE

    def norm_set(items):
        return {" ".join(str(x).lower().split()) for x in items
                if isinstance(x, str)}

    def jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 1.0
        return len(a & b) / max(1, len(a | b))
    scores = {}
    for key in ("components", "entities", "routes", "state_transitions",
                "dependencies"):
        got = norm_set(plan.get(key, []) if isinstance(plan.get(key), list)
                       else [])
        want = norm_set(ref[key])
        if key in ("entities", "dependencies"):
            scores[key] = round(len(got & want) / len(want), 3)
        else:
            scores[key] = round(jaccard(got, want), 3)
    return {"valid_json": True, "scores": scores, "plan": plan}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command",
                    choices=["fingerprint", "stage-a", "develop", "holdout",
                             "smoke"])
    ap.add_argument("--role", choices=list(contracts.ROLES))
    ap.add_argument("--docs", action="store_true",
                    help="documentation retrieval condition")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--wall", type=int, default=WALL_BUDGET_ROLE)
    ap.add_argument("--state",
                    default=str(EXP / "state.json"))
    args = ap.parse_args()

    if args.command == "fingerprint":
        print(json.dumps({
            "contract_fingerprint": contracts.fingerprint(),
            "holdout_digest": contracts.holdout_digest(),
            "version": contracts.VERSION,
        }, indent=1))
        return

    if args.command == "smoke":
        # worker round-trip without any model: trusted reference modules
        good_store = Path(ROOT / "archagent" / "_selftest_store.js")
        print("selftest files are generated by tests; see tests/test_archagent.py")
        return

    if args.command == "stage-a":
        from archagent.model import FrozenModel
        model = FrozenModel()
        out, usage = model.generate(contracts.prompt("stage_a"),
                                    max_tokens=GEN_TOKENS["stage_a"], seed=1)
        scored = score_stage_a(out)
        report = {"stage": "A", "plan_raw": out, "usage": usage,
                  **scored, "model_usage": model.usage()}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "stage_a.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        print(json.dumps({k: v for k, v in scored.items() if k != "plan"},
                         indent=1))
        print("saved", REPORTS / "stage_a.json")
        return

    if args.command == "holdout":
        state = _load_state(args.state)
        selected = state.get("selected", {})
        missing = [r for r in ("logic", "store", "api") if r not in selected]
        if missing:
            raise SystemExit(f"missing selected modules: {missing}")
        report = {"phase": "holdout", "digest": contracts.holdout_digest(),
                  "roles": {}}
        for role in ("logic", "store", "api"):
            r = evaluate_module(
                role, selected[role]["source"],
                store_source=selected["store"]["source"] if role == "api" else None,
                logic_source=selected["logic"]["source"] if role == "api" else None,
                phase="holdout", timeout=90)
            sc = score_of(r)
            report["roles"][role] = {
                "checks_passed": sc[0], "checks_total": sc[1],
                "checks": r.get("checks", {}),
                "failures": r.get("failures", [])[:6],
                "error": r.get("error")}
            print(role, sc, flush=True)
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "holdout_evaluation.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        print("saved", REPORTS / "holdout_evaluation.json")
        return

    if args.command == "develop":
        if not args.role:
            ap.error("--role is required for develop")
        from archagent.model import FrozenModel
        model = FrozenModel()
        memory = RepairMemory(str(MEMORY))
        state = _load_state(args.state)
        deps = {}
        if args.role == "api":
            if "store" not in state.get("selected", {}):
                raise SystemExit("develop store first (api depends on it)")
            deps["store_source"] = state["selected"]["store"]["source"]
            if "logic" in state.get("selected", {}):
                deps["logic_source"] = state["selected"]["logic"]["source"]
        harness = Harness(model, docs=args.docs, memory=memory)
        result = harness.develop(args.role, max_rounds=args.max_rounds,
                                 wall=args.wall, **deps)
        report = {
            "role": args.role, "stopped": result["stopped"],
            "wall_seconds": result["wall"], "usage": result["usage"],
            "best": {"attempt_id": result["best"]["attempt_id"],
                     "score": result["score"] if "score" in result else
                     result["best"]["score"],
                     "source_sha256": sha(result["best"]["source"] or ""),
                     "result": {k: result["best"]["result"].get(k)
                                for k in ("passed", "syntax_valid", "checks",
                                          "failures", "error")}},
            "attempts": result["attempts"],
        }
        REPORTS.mkdir(parents=True, exist_ok=True)
        tag = "docs" if args.docs else "nodocs"
        (REPORTS / f"develop_{args.role}_{tag}.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        state.setdefault("selected", {})[args.role] = {
            "source": result["best"]["source"],
            "attempt_id": result["best"]["attempt_id"],
            "score": list(result["best"]["score"]),
            "origin": "pending-lineage-verification",
        }
        _save_state(args.state, state)
        print("role", args.role, "stopped:", result["stopped"],
              "score:", result["best"]["score"])
        print("saved report; state updated")
        return


def _load_state(path: str) -> dict:
    p = Path(path)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf8"))
    return {"contract_fingerprint": contracts.fingerprint(),
            "holdout_digest": contracts.holdout_digest(),
            "selected": {}}


def _save_state(path: str, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=1) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
