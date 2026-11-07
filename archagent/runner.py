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
GEN_TOKENS = {"logic": 600, "store": 1300, "api": 1400, "ui": 1500,
              "css": 500, "stage_a": 420}

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


def semantic_anchor(source: str, result: dict) -> int | None:
    """For value-mismatch failures (no exception line), anchor at the
    assignment line of the identifier the failure mentions."""
    import re as _re
    blob = json.dumps(result.get("failures", []))
    ids = []
    for name in ("by_priority", "by_status", "percent", "remaining",
                 "total", "done"):
        if name in blob:
            ids.append(name)
    lines = source.splitlines()
    for name in ids:
        pat = _re.compile(rf"^\s*(?:const|let|var)?\s*{name}\s*=|^\s*{name}\s*=")
        for i, line in enumerate(lines, 1):
            if pat.match(line):
                return i
    return None


def failing_line(result: dict) -> int | None:
    err = result.get("error") or ""
    m = re.search(r"qwen-[a-z]+\.js:(\d+):(\d+)", err)
    if m:
        return int(m.group(1))
    for f in result.get("failures", []):
        detail = str(f.get("detail", ""))
        m = re.search(r"at line (\d+)", detail)
        if m:
            return int(m.group(1))
        m = re.search(r"@?line (\d+)", detail)
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
    (re.compile(r"string indices must be integers|iterating a dict", re.I),
     "payload is a dict; iterating it yields its KEYS (strings). The task "
     "list is the value: tasks = payload[\"tasks\"]."),
    (re.compile(r"KeyError", re.I),
     "Initialize every output key before the loop (by_priority = "
     "{\"low\": 0, \"medium\": 0, \"high\": 0}, by_status = {\"todo\": 0, "
     "\"doing\": 0, \"done\": 0}) so counts start at zero and every key "
     "is always present."),
    (re.compile(r"ZeroDivisionError|division by zero", re.I),
     "When total is 0 the percent must be 0: use "
     "percent = round(100 * done / total) if total else 0."),
    (re.compile(r"percent.{0,12}(1[0-9]{2}|[2-9][0-9]{2})|remaining.{0,8}:", re.I),
     "remaining = total - done (the tasks not done yet); percent = "
     "round(100 * done / total) and can never exceed 100."),
    (re.compile(r"by_priority.{0,40}(done|todo|doing)|by_status.{0,40}(low|medium|high)", re.I),
     "by_priority counts task[\"priority\"] values (low/medium/high); "
     "by_status counts task[\"status\"] values (todo/doing/done). They "
     "are different fields of each task."),
    (re.compile(r'expected .{0,40}"id": ?"p1".{0,60}got .{0,40}"id": ?"?"1', re.I),
     "Project ids are the string 'p' + counter ('p1', 'p2'); task ids 't' + "
     "counter ('t1', 't2'); createdAt is always the fixed string "
     "'2026-11-07', never new Date()."),
    (re.compile(r"Cannot read properties of undefined", re.I),
     "Find the record before mutating it: const rec = list.find(x => x.id "
     "=== String(id)); if (!rec) throw Error('not found: ' + id)."),
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
    c = "#" if role == "logic" else "//"
    expected = ""
    m = re.search(r"e\.g\. (\{.*?\})(?:\s|$)", detail)
    if m:
        expected = (f"\n{c} The expected output for that case starts: "
                    + m.group(1)[:180])
    return (f"\n{c} FIX the code in the gap. Failure: "
            + str(f.get("check") if f else "")
            + " " + detail[:200].replace("\n", " ")
            + expected
            + (f"\n{c} Concept: " + concept if concept else "")
            + f"\n{c} Output ONLY the replacement code for the gap.{c}\n")


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
        self._gen_cache: dict[str, str] = {}
        self.log = GEN / ("generations_docs.jsonl" if docs else "generations.jsonl")
        GEN.mkdir(parents=True, exist_ok=True)

    def record(self, entry: dict) -> None:
        with open(self.log, "a", encoding="utf8") as f:
            f.write(json.dumps(entry) + "\n")

    def burst(self, role: str, n: int = 10, *, store_source=None,
              logic_source=None, base_seed: int = 90000,
              on_sample=None) -> dict:
        """High-temperature sampling burst from the round-0 prompt.

        Bounded stochastic search: the repair loop anchors the model to its
        own broken structure; fresh diverse completions of the original
        contract prompt explore structurally different solutions."""
        prompt = contracts.prompt(
            role, docs=retrieval.doc_block(role) if self.docs else "")
        best = {"source": None, "result": None, "score": (-1, -1),
                "attempt_id": None}
        for k in range(n):
            completion, usage = self.model.generate(
                prompt, max_tokens=GEN_TOKENS[role],
                seed=base_seed + k, stochastic=True)
            if _degenerate(completion):
                continue
            source = _post_process(role, completion)
            result = evaluate_module(role, source,
                                     store_source=store_source,
                                     logic_source=logic_source)
            sc = score_of(result)
            attempt_id = f"{role}-burst-{base_seed + k}"
            self.record({
                "id": attempt_id, "role": role, "round": "burst",
                "kind": "burst", "seed": base_seed + k, "stochastic": True,
                "usage": usage, "checks_passed": sc[0],
                "checks_total": sc[1],
                "syntax_valid": result.get("syntax_valid"),
                "accepted": False, "origin": {"type": "burst"},
                "source_sha256": sha(source), "source": source,
                "failures": result.get("failures", [])[:8],
                "error": result.get("error"),
            })
            if sc > best["score"]:
                best = {"source": source, "result": result, "score": sc,
                        "attempt_id": attempt_id}
                print(f"  [{role}] burst {k} -> {sc[0]}/{sc[1]}", flush=True)
                if on_sample is not None:
                    on_sample(role, best)
            if sc[1] and sc[0] == sc[1]:
                break
        return best

    def develop(self, role: str, *, store_source=None, logic_source=None,
                max_rounds=MAX_ROUNDS, wall=WALL_BUDGET_ROLE,
                resume_state: dict | None = None,
                on_round_end=None) -> dict:
        t0 = time.time()
        best = {"source": None, "result": None, "score": (-1, -1),
                "attempt_id": None}
        attempts = []
        round_i = 0
        stopped = None
        if resume_state and resume_state.get("best", {}).get("source"):
            best = {
                "source": resume_state["best"]["source"],
                "result": resume_state["best"].get("result"),
                "score": tuple(resume_state["best"].get("score", (-1, -1))),
                "attempt_id": resume_state["best"].get("attempt_id"),
            }
            round_i = int(resume_state.get("round", 0))
            attempts = list(resume_state.get("attempts", []))
            print(f"  [{role}] resuming from round {round_i} "
                  f"(best {best['score']})", flush=True)
            if best["result"] is None:
                # re-evaluate the resumed best to rebuild failure feedback
                best["result"] = evaluate_module(
                    role, best["source"], store_source=store_source,
                    logic_source=logic_source)
                best["score"] = score_of(best["result"])
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
                browser_feedback = os.environ.get("BROWSER_FEEDBACK", "")
                full_feedback = feedback
                if browser_feedback:
                    full_feedback = (feedback + " | REAL BROWSER TEST "
                                     "FEEDBACK: " + browser_feedback)[:700]
                rp = contracts.prompt(
                    role,
                    docs=retrieval.doc_block(role) if self.docs else "",
                    feedback=full_feedback,
                    previous_excerpt=_prev_excerpt(prev, res, hide_full),
                    self_note=mem_block.rstrip() if mem_block else "",
                    concept=_concept_note(role, res))
                candidates.append(("whole-greedy", rp, round_i * 1000, False))
                for k in range(2):
                    candidates.append(("whole-sample", rp,
                                       round_i * 1000 + 10 + k, True))
                anchor = failing_line(res) or semantic_anchor(prev, res)
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
                    if _degenerate(fill) or _echoes_instructions(fill, instr):
                        fill, usage = self.model.fim(
                            prefix, suffix, instructions=instr,
                            max_tokens=320, seed=seed + 500, stochastic=True)
                    if _echoes_instructions(fill, instr):
                        continue  # both attempts echoed; skip this candidate
                    source = splice(best["source"], fill, lo, hi)
                    origin = {"type": "fim", "base_sha256": sha(best["source"]),
                              "fill": fill[:2000], "anchor_line": lo + 1,
                              "seed": seed}
                else:
                    _, prompt, seed, stoch = cand
                    key = sha(prompt) + f"#{seed}#{stoch}"
                    if key in self._gen_cache:
                        completion = self._gen_cache[key]
                        usage = {"tokens": 0, "seconds": 0.0, "seed": seed,
                                 "stochastic": stoch, "cached": True}
                    else:
                        completion, usage = self.model.generate(
                            prompt, max_tokens=GEN_TOKENS[role], seed=seed,
                            stochastic=stoch)
                        if _degenerate(completion):
                            completion, usage = self.model.generate(
                                prompt, max_tokens=GEN_TOKENS[role],
                                seed=seed + 500, stochastic=True)
                        self._gen_cache[key] = completion
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
            if not improved and round_i > 0 and round_i >= 5 and \
                    best["score"][0] == 0:
                stopped = "plateau-zero"; break
            round_i += 1
            if on_round_end is not None:
                on_round_end(role, round_i, best, attempts)
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


def _echoes_instructions(fill: str, instructions: str) -> bool:
    """True when the fill copied the instruction comment lines instead of
    writing code (measured failure mode of the frozen model)."""
    instr_words = [w for w in instructions.split() if len(w) > 6]
    if not instr_words or not fill.strip():
        return True
    fill_words = set(fill.split())
    overlap = sum(1 for w in instr_words if w in fill_words)
    return overlap / len(instr_words) > 0.5


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

def _balanced_braces(text: str) -> str | None:
    depth, start = 0, None
    in_str = None
    for i, ch in enumerate(text):
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in "\"'":
            in_str = ch
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start:i + 1]
    return None


def _tolerant_load(block: str):
    """Deterministic parse tolerance for near-JSON model output (single
    quotes, trailing commas, unquoted keys).  Scaffold extraction only;
    never alters the recorded raw bytes."""
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", block)
    fixed = fixed.replace("'", '"')
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # quote bare keys
    fixed2 = re.sub(r"(\{|,\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:",
                    r'\1"\2":', fixed)
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        return None


def score_stage_a(plan_text: str) -> dict:
    block = _balanced_braces(plan_text)
    if block is None:
        return {"valid_json": False, "scores": {}, "raw": plan_text[:300]}
    plan = _tolerant_load(block)
    if plan is None or not isinstance(plan, dict):
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
                             "build-store", "build-api", "build-ui",
                             "repair-ui-piece", "smoke"])
    ap.add_argument("--role", choices=list(contracts.ROLES))
    ap.add_argument("--docs", action="store_true",
                    help="documentation retrieval condition")
    ap.add_argument("--burst", type=int, default=0,
                    help="run N high-temperature samples from the round-0 "
                         "prompt before the repair loop")
    ap.add_argument("--burst-seed", type=int, default=90000,
                    help="base seed for the burst samples")
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
        attempts = []
        scored = None
        # bounded candidate search: 1 greedy + 2 sampled (mission budget)
        for seed, stoch in ((1, False), (11, True), (12, True)):
            out, usage = model.generate(contracts.prompt("stage_a"),
                                        max_tokens=GEN_TOKENS["stage_a"],
                                        seed=seed, stochastic=stoch)
            # the prompt ends with the opening '{' (anchor); the completion
            # continues the object, so restore it before parsing
            scored = score_stage_a("{" + out)
            attempts.append({"seed": seed, "stochastic": stoch,
                             "usage": usage,
                             "valid_json": scored["valid_json"]})
            if scored["valid_json"]:
                break
        report = {"stage": "A", "attempts": attempts,
                  "model_usage": model.usage(), **scored}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "stage_a.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        print(json.dumps({k: v for k, v in scored.items()
                          if k not in ("plan", "raw")}, indent=1))
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

    if args.command == "build-store":
        from archagent.model import FrozenModel
        from archagent.store_builder import build_store
        model = FrozenModel()
        memory = RepairMemory(str(MEMORY))
        state = _load_state(args.state)
        log_path = GEN / "generations_docs.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def log(entry):
            with open(log_path, "a", encoding="utf8") as f:
                f.write(json.dumps(entry) + "\n")

        resume = state.get("staged_store_pieces")
        def checkpoint(pieces_):
            state["staged_store_pieces"] = pieces_
            _save_state(args.state, state)
        out = build_store(model, log, docs=True, wall=args.wall,
                          resume=resume, on_piece=checkpoint)
        report = {"ok": out["ok"], "score": list(out.get("score", ())),
                  "pieces": {k: len(v.splitlines()) for k, v in
                             out.get("pieces", {}).items()},
                  "failures": out.get("result", {}).get("failures", [])[:8],
                  "usage": model.usage()}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "build_store_staged.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        if out.get("source"):
            state.setdefault("selected", {})["store"] = {
                "source": out["source"],
                "attempt_id": "staged-assembly-final",
                "score": list(out.get("score", ())),
                "origin": "QWEN-REPAIRED (staged pieces, see generations)",
            }
            state.setdefault("in_progress", {}).pop("store", None)
            _save_state(args.state, state)
        print(json.dumps(report, indent=1)[:600])
        return

    if args.command == "build-api":
        from archagent.model import FrozenModel
        from archagent.api_builder import build_api
        model = FrozenModel()
        state = _load_state(args.state)
        sel = state.get("selected", {})
        if "store" not in sel:
            raise SystemExit("build-store must pass first")
        log_path = GEN / "generations_docs.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def log(entry):
            with open(log_path, "a", encoding="utf8") as f:
                f.write(json.dumps(entry) + "\n")

        def checkpoint(pieces_):
            state["staged_api_pieces"] = pieces_
            _save_state(args.state, state)

        out = build_api(model, log,
                        store_source=sel["store"]["source"],
                        logic_source=sel.get("logic", {}).get("source"),
                        docs=True, wall=args.wall,
                        resume=state.get("staged_api_pieces"),
                        on_piece=checkpoint)
        report = {"ok": out["ok"], "score": list(out.get("score", ())),
                  "pieces": list(out.get("pieces", {}).keys()),
                  "failures": out.get("result", {}).get("failures", [])[:8],
                  "usage": model.usage()}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "build_api_staged.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        if out.get("source"):
            state.setdefault("selected", {})["api"] = {
                "source": out["source"],
                "attempt_id": "api-staged-assembly-final",
                "score": list(out.get("score", ())),
                "origin": "QWEN (staged route pieces)",
            }
            state.setdefault("in_progress", {}).pop("api", None)
            _save_state(args.state, state)
        print(json.dumps(report, indent=1)[:500])
        return

    if args.command == "build-ui":
        from archagent.model import FrozenModel
        from archagent.ui_builder import build_ui
        model = FrozenModel()
        state = _load_state(args.state)
        log_path = GEN / "generations_docs.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def log(entry):
            with open(log_path, "a", encoding="utf8") as f:
                f.write(json.dumps(entry) + "\n")

        def checkpoint(pieces_):
            state["staged_ui_pieces"] = pieces_
            _save_state(args.state, state)

        out = build_ui(model, log, docs=True, wall=args.wall,
                       resume=state.get("staged_ui_pieces"),
                       on_piece=checkpoint)
        report = {"ok": out["ok"], "score": list(out.get("score", ())),
                  "pieces": list(out.get("pieces", {}).keys()),
                  "failures": out.get("result", {}).get("failures", [])[:8],
                  "usage": model.usage()}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "build_ui_staged.json").write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf8")
        if out.get("source"):
            state.setdefault("selected", {})["ui"] = {
                "source": out["source"],
                "attempt_id": "ui-staged-assembly-final",
                "score": list(out.get("score", ())),
                "origin": "QWEN (staged ui pieces)",
            }
            state.setdefault("in_progress", {}).pop("ui", None)
            _save_state(args.state, state)
        print(json.dumps(report, indent=1)[:500])
        return

    if args.command == "repair-ui-piece":
        # re-burst ONE ui piece with execution feedback (browser test
        # failures feed back into the loop; the piece stays model bytes)
        from archagent.model import FrozenModel
        from archagent.ui_builder import (build_ui, PIECE_ANCHORS,
                                          HANDLER_SPECS, piece_prompt,
                                          piece_gate, assemble,
                                          _extract_plain_piece,
                                          _extract_jsx_piece)
        from archagent.runner import _degenerate
        import archagent.ui_builder as ub
        model = FrozenModel()
        state = _load_state(args.state)
        pieces = state.get("staged_ui_pieces", {})
        name = os.environ.get("PIECE", "")
        feedback = os.environ.get("FEEDBACK", "")
        if name not in PIECE_ANCHORS:
            raise SystemExit(f"unknown piece {name}")
        order = ["state"] + ub.HANDLER_PIECES + ["jsx"]
        accepted_before = "".join(pieces.get(m, "") for m in order
                                  if m != name)
        prompt = piece_prompt(name, accepted_before, True)
        if feedback:
            prompt = prompt.replace(
                "\n" + PIECE_ANCHORS[name],
                contracts.commentize(
                    "ui", "PUBLIC CHECK FEEDBACK: " + feedback) +
                "\n" + PIECE_ANCHORS[name])
        log_path = GEN / "generations_docs.jsonl"
        best = None
        for k in range(6):
            seed = 300000 + (int(time.time() * 7) % 89000) + k * 11
            completion, usage = model.generate(
                prompt, max_tokens=1100 if name == "jsx" else 950,
                seed=seed, stochastic=True)
            if _degenerate(completion):
                continue
            body = (_extract_jsx_piece(completion) if name == "jsx"
                    else _extract_plain_piece(completion, name))
            with open(log_path, "a", encoding="utf8") as f:
                f.write(json.dumps({
                    "id": f"ui-repair-{name}-{seed}", "role": "ui",
                    "round": f"repair-{name}", "kind": "repair-piece",
                    "seed": seed, "stochastic": True, "usage": usage,
                    "checks_passed": None, "checks_total": None,
                    "syntax_valid": None, "accepted": False,
                    "origin": {"type": "repair", "piece": name,
                               "feedback": feedback[:200]},
                    "source_sha256": sha(body), "source": body,
                    "failures": [], "error": None}) + "\n")
            gate = piece_gate(name, body)
            if gate:
                print(f"  [repair/{name}] sample {k} gate: {gate}")
                continue
            best = body
            break
        if best is None:
            raise SystemExit("repair found no valid sample")
        pieces[name] = best
        state["staged_ui_pieces"] = pieces
        module = assemble(pieces)
        # verify the full offline checks still pass
        res = evaluate_module("ui", module, timeout=60)
        sc = score_of(res)
        print(f"  [repair/{name}] offline checks {sc[0]}/{sc[1]}")
        if sc[1] == 0 or sc[0] != sc[1]:
            raise SystemExit("repair broke offline checks; not applied")
        state.setdefault("selected", {})["ui"] = {
            "source": module,
            "attempt_id": f"ui-repair-{name}-final",
            "score": list(sc),
            "origin": "QWEN-REPAIRED (browser-feedback repair)",
        }
        _save_state(args.state, state)
        print("repair applied; ui module updated")
        return

    if args.command == "develop":
        if not args.role:
            ap.error("--role is required for develop")
        role = args.role
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
        in_progress = state.get("in_progress", {}).get(args.role)
        if args.burst > 0:
            def burst_checkpoint(r_, best_):
                cur = (state.get("in_progress", {}).get(r_) or {}) \
                    .get("best", {})
                if tuple(cur.get("score", (-1, -1))) < best_["score"]:
                    state.setdefault("in_progress", {})[r_] = {
                        "best": {"source": best_["source"],
                                 "score": list(best_["score"]),
                                 "attempt_id": best_["attempt_id"]},
                        "round": 1,
                        "attempts": [best_["attempt_id"]]}
                    _save_state(args.state, state)
            burst_best = harness.burst(role, args.burst,
                                       base_seed=args.burst_seed,
                                       on_sample=burst_checkpoint)
            if burst_best["source"] is not None:
                cur = (in_progress or {}).get("best", {})
                if tuple(cur.get("score", (-1, -1))) < burst_best["score"]:
                    state.setdefault("in_progress", {})[args.role] = {
                        "best": {"source": burst_best["source"],
                                 "score": list(burst_best["score"]),
                                 "attempt_id": burst_best["attempt_id"]},
                        "round": 1, "attempts": [burst_best["attempt_id"]],
                    }
                    _save_state(args.state, state)
                    in_progress = state["in_progress"][args.role]
                    print(f"burst best {burst_best['score']} stored")

        def checkpoint(role, round_i, best, attempts):
            state.setdefault("in_progress", {})[role] = {
                "best": {"source": best["source"],
                         "score": list(best["score"]),
                         "attempt_id": best["attempt_id"]},
                "round": round_i, "attempts": attempts[-40:],
            }
            _save_state(args.state, state)

        result = harness.develop(args.role, max_rounds=args.max_rounds,
                                 wall=args.wall, resume_state=in_progress,
                                 on_round_end=checkpoint, **deps)
        # keep in_progress unless the role fully passed, so a later
        # invocation can continue improving the same best candidate
        if result["stopped"] == "pass":
            state.setdefault("in_progress", {}).pop(args.role, None)
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
