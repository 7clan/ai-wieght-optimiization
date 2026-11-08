"""Staged CSS builder — Session 034.

Generates the application stylesheet piece by piece with the frozen
Qwen2.5-Coder-0.5B, exactly like the Session 033 store/api builders:

  prompt = concept + worked example (different domain) + measurable
           requirements + anchor (the selector line)
  acceptance = static structural gates + REAL headless-browser harness
               criteria (archagent/visual/check_component.mjs)
  repair = execution-guided: the model sees its own previous bytes plus
           the failing check names/details, then retries (bounded)
  attribution = QWEN-ORIGINAL if accepted from the plain burst,
               QWEN-REPAIRED if accepted after feedback

Every generation (accepted or not) is recorded under
experiments/zai-visual/generations/ with prompt, seed, token count and
gate results.  No teacher CSS is ever written: the builder only
assembles verified model bytes.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.visual import curriculum  # noqa: E402

GEN_DIR = ROOT / "experiments" / "zai-visual" / "generations"
CUR_DIR = ROOT / "experiments" / "zai-visual" / "curriculum"
CHECK = ROOT / "archagent" / "visual" / "check_component.mjs"
NODE_ENV = dict(PATH="/usr/local/bin:/usr/bin:/bin",
                PLAYWRIGHT_BROWSERS_PATH="/home/z/.cache/ms-playwright")


def sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def balanced_block(text: str) -> str | None:
    """Longest prefix of `text` whose braces balance (>= 1 closed pair)."""
    depth, end = 0, None
    in_str, in_comment = None, False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_comment:
            if ch == "*" and nxt == "/":
                in_comment = False; i += 2; continue
            i += 1; continue
        if in_str:
            if ch == in_str:
                in_str = None
            i += 1; continue
        if ch == "/" and nxt == "*":
            in_comment = True; i += 2; continue
        if ch in "\"'":
            in_str = ch; i += 1; continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
        i += 1
    return text[:end] if end else None


def cut_trailing_prose(code: str) -> str:
    """Keep only the leading run of well-formed CSS rules.

    Forward state machine: while at rule-boundary depth 0, a line must
    be blank, a comment, a selector opening '{', or (at rule start) a
    declaration line.  The FIRST prose line (English explanation,
    quoted checker output, etc.) ends the stylesheet — everything from
    there on is dropped, so prose that later embeds quoted CSS blocks
    cannot leak back in.
    """
    lines = code.splitlines()
    kept = []          # committed lines
    pend = []          # blanks/comments waiting for the next rule
    depth = 0
    for ln in lines:
        s = ln.strip()
        if depth == 0:
            if s == '' or s.startswith('/*') or s.startswith('//'):
                pend.append(ln)
                continue
            if '{' in s:
                kept += pend
                pend = []
                depth = s.count('{') - s.count('}')
                kept.append(ln)
                continue
            if re.match(r'^[a-zA-Z-]+\s*:\s*[^;{}]+;?\s*$', s):
                # top-level declaration (only valid right after an anchor
                # opened a block we did not see); keep it
                kept += pend
                pend = []
                kept.append(ln)
                continue
            # prose → stop here
            break
        else:
            kept.append(ln)
            depth += s.count('{') - s.count('}')
            if depth < 0:
                depth = 0
    # drop trailing blank/comment run after the last real rule
    while kept and (kept[-1].strip() == '' or
                    kept[-1].strip().startswith('/*') or
                    kept[-1].strip().startswith('//')):
        kept.pop()
    out = '\n'.join(kept)
    return out if re.search(r'[};]\s*$', out) else code


def strip_prose(completion: str, anchor: str = "") -> str:
    """Drop markdown fences / leading prose; dedupe anchor repetition."""
    text = completion
    if "```" in text:
        parts = text.split("```")
        blocks = [p for p in parts[1::2] if "{" in p or ":" in p]
        if blocks:
            text = blocks[0].removeprefix("css").removeprefix("CSS")
    # if the model repeats the anchor's first line, drop the duplicate
    first_anchor = anchor.split("\n")[0].strip() if anchor else ""
    lines = text.splitlines()
    while lines and first_anchor and lines[0].strip() == first_anchor:
        lines = lines[1:]
    # keep lines from the first '{'-bearing or declaration-like line on
    out = []
    started = False
    for ln in lines:
        if not started and ("{" in ln or re.match(r"^\s*[.#@:a-zA-Z*]", ln)
                            and not re.match(r"^\s*(//|Your|Here|TASK|Now|Note|The |Write|First)", ln)):
            started = True
        if started:
            out.append(ln)
    return "\n".join(out).strip()


def degenerate(text: str) -> bool:
    """Repetition / emptiness guards (mirrors runner._degenerate)."""
    if len(text.strip()) < 20:
        return True
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 4:
        uniq = len(set(lines))
        if uniq / len(lines) < 0.5:
            return True
    # one selector repeated with identical body
    bodies = re.findall(r"\{([^{}]*)\}", text)
    if len(bodies) >= 3 and len(set(b.strip() for b in bodies)) == 1:
        return True
    return False


# Common CSS declaration vocabulary — legitimate in any rule body, so
# excluded from spec-echo overlap (a CSS patch that says "font-size" is
# writing code, not echoing the requirement text).
CSS_VOCAB = {
    "font", "size", "color", "family", "weight", "height", "width",
    "padding", "margin", "border", "radius", "background", "solid",
    "none", "center", "space", "between", "pointer", "hidden",
    "visible", "flex", "grid", "inline", "block", "items", "align",
    "justify", "content", "display", "overflow", "text", "decoration",
    "line", "letter", "spacing", "min-height", "min-width", "max-width",
    "auto", "transparent", "inherit", "initial", "relative", "absolute",
    "fixed", "sticky", "left", "right", "top", "bottom", "inside",
    "outside", "large", "small", "larger", "smaller", "medium",
}


def echoes(completion: str, spec: str, anchor: str = "") -> bool:
    """Reject spec-echo (model quoting the instructions, not CSS).

    Words that appear in the ANCHOR are excluded: the anchor is the
    interface contract (selector names, property names) — writing those
    is required, not echoing.  CSS_VOCAB likewise covers the standard
    declaration vocabulary.  For tiny CSS patches the body vocabulary
    is legitimately a near-subset of the spec's, so without these
    exclusions the check is mathematically guaranteed to misfire.
    """
    rules = re.findall(r"\{([^{}]*)\}", completion)
    if not rules:
        return True
    anchor_words = set(re.findall(r"[a-z]{4,}", anchor.lower()))
    spec_words = (set(re.findall(r"[a-z]{4,}", spec.lower()))
                  - CSS_VOCAB - anchor_words)
    for body in rules[:3]:
        decls = [d for d in body.split(";") if ":" in d]
        if not decls:
            continue
        words = (set(re.findall(r"[a-z]{4,}", body.lower()))
                 - CSS_VOCAB - anchor_words)
        if not words:
            continue
        overlap = len(words & spec_words) / len(words)
        if overlap > 0.6:
            return True
    return False


def static_gates(code: str, task: dict) -> list[str]:
    """Structural gates on the ASSEMBLED piece (anchor + completion).
    Returns list of failure strings (empty = pass)."""
    fails = []
    if balanced_block(code) is None:
        fails.append("braces do not balance")
    st = task.get("static", {})
    for sel in st.get("require_selectors", []):
        if sel not in code:
            fails.append(f"missing selector {sel!r}")
    for var in st.get("require_vars", []):
        if not re.search(re.escape(var) + r"\s*:", code):
            fails.append(f"missing token {var}")
    for word in st.get("forbid", []):
        if word in code:
            fails.append(f"forbidden pattern {word!r}")
    for marker in curriculum.DEMO_MARKERS:
        if marker in code:
            fails.append(f"echoed the demo example ({marker})")
    if re.search(r"display:\s*none", code) and "skeleton" not in code and "modal" not in code:
        fails.append("display:none on interactive surface")
    return fails


# Per-task generation budgets (the tokens block is the largest piece).
MAX_TOKENS_OVERRIDE = {"tokens": 750}


class CSSBuilder:
    def __init__(self, model, harness_base: str, css_path: Path,
                 state_path: Path | None = None,
                 gen_prefix: str = "css"):
        self.model = model
        self.base = harness_base
        self.css_path = css_path
        self.state_path = state_path or (CUR_DIR / "state.json")
        self.gen_prefix = gen_prefix
        self.state = {"pieces": {}, "log": []}
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text())
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        CUR_DIR.mkdir(parents=True, exist_ok=True)
        self.n_gen = 0

    # -- helpers -------------------------------------------------------

    def _record(self, task_id: str, kind: str, prompt: str, text: str,
                usage: dict, gates: list, harness: dict | None) -> dict:
        self.n_gen += 1
        rec = dict(task=task_id, kind=kind, sha256=sha(text),
                   prompt_sha256=sha(prompt), usage=usage,
                   static_gates=gates, harness=harness,
                   text=text)
        path = GEN_DIR / f"{self.gen_prefix}_{task_id}_{self.n_gen:03d}.json"
        path.write_text(json.dumps(rec, indent=1))
        return rec

    def _harness_check(self, task: dict, code: str) -> dict:
        """Assemble accepted pieces + candidate, then run the browser gate."""
        accepted = "\n\n".join(
            self.state["pieces"][tid]["code"]
            for tid in curriculum.TASK_IDS
            if tid in self.state["pieces"])
        css = accepted + "\n\n" + code + "\n"
        self.css_path.write_text(css)
        out = subprocess.run(
            ["node", str(CHECK), "--base", self.base,
             "--task", task["harness"],
             "--out", str(CUR_DIR / "_last_check.json")],
            capture_output=True, text=True, timeout=120, env=NODE_ENV,
            cwd=str(ROOT))
        try:
            rep = json.loads((CUR_DIR / "_last_check.json").read_text())
        except Exception:
            rep = None
        # check_component prints; parse exit + derive from stdout lines
        ok = out.returncode == 0
        fails = [l for l in out.stdout.splitlines() if l.strip().startswith("FAIL")]
        return {"ok": ok, "fails": fails, "stdout": out.stdout[-2000:],
                "report": rep}

    # -- main loop -----------------------------------------------------

    def build_task(self, task_id: str, *, burst: int = 6,
                   repair_rounds: int = 2, max_tokens: int = 520,
                   verbose: bool = True) -> dict | None:
        task = curriculum.task_by_id(task_id)
        if task_id in self.state["pieces"]:
            if verbose:
                print(f"[{task_id}] already accepted (checkpoint)")
            return self.state["pieces"][task_id]

        feedback = None
        own_previous = None
        t0 = time.time()
        accepted = None
        round_no = 0
        attribution = "QWEN-ORIGINAL"
        attempts = 0

        while accepted is None and round_no <= repair_rounds:
            for k in range(burst):
                attempts += 1
                prompt = curriculum.piece_prompt(
                    task, feedback=feedback, own_previous=own_previous)
                budget = MAX_TOKENS_OVERRIDE.get(task_id, max_tokens)
                # sampling FIRST (greedy loops on this base model — the
                # Session-033 measurement); greedy kept as a late candidate
                order = list(range(1, burst)) + [0] if burst > 1 else [0]
                k_eff = order[k] if k < len(order) else k
                seed = k_eff * 1013 + round_no * 77
                stochastic = k_eff != 0
                text, usage = self.model.generate(
                    prompt, max_tokens=budget, seed=seed,
                    stochastic=stochastic)
                # ASSEMBLE: the anchor (interface contract) + model bytes
                code = task["anchor"] + strip_prose(text, task["anchor"])
                block = balanced_block(code)
                gates = static_gates(code, task)
                harness = None
                if block and not gates and not degenerate(code) \
                        and not echoes(code, task["spec"]):
                    code = block  # cut at the last complete rule
                    harness = self._harness_check(task, code)
                    if harness["ok"]:
                        accepted = code
                        break
                self._record(task_id,
                             "burst" if round_no == 0 else "repair",
                             prompt, code, usage, gates, harness)
                if verbose:
                    why = ("gates:" + ";".join(gates[:3]) if gates else
                           ("degenerate" if degenerate(code) else
                            ("echo" if echoes(code, task["spec"]) else
                             ("unbalanced" if not block else
                              (f"harness:{len(harness['fails'])}f"
                               if harness else "?")))))
                    print(f"[{task_id}] try {attempts} ({why}) "
                          f"{usage['tokens']}tok {usage['seconds']}s")
            if accepted is None and round_no < repair_rounds:
                # build feedback from the best failing harness run
                last = self._last_harness_fail(task_id)
                if last:
                    feedback = last
                    own_previous = self._last_candidate(task_id)
                round_no += 1
                attribution = "QWEN-REPAIRED"
            else:
                break

        dt = round(time.time() - t0, 1)
        if accepted is None:
            self.state["log"].append(
                dict(task=task_id, ok=False, attempts=attempts, seconds=dt))
            self._save()
            if verbose:
                print(f"[{task_id}] FAILED after {attempts} attempts ({dt}s)")
            return None

        rec = dict(code=accepted, sha256=sha(accepted), attempts=attempts,
                   attribution=attribution, seconds=dt,
                   accepted_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.state["pieces"][task_id] = rec
        self.state["log"].append(dict(task=task_id, ok=True,
                                      attempts=attempts, attribution=attribution,
                                      seconds=dt))
        self._save()
        if verbose:
            print(f"[{task_id}] ACCEPTED ({attribution}) after {attempts} "
                  f"attempts ({dt}s, {len(accepted.splitlines())} lines)")
        return rec

    def _last_harness_fail(self, task_id: str) -> str | None:
        files = sorted(GEN_DIR.glob(f"{self.gen_prefix}_{task_id}_*.json"))
        for f in reversed(files):
            rec = json.loads(f.read_text())
            if rec.get("harness") and not rec["harness"]["ok"]:
                return "\n".join(rec["harness"]["fails"][:6]) or "no output"
        return None

    def _last_candidate(self, task_id: str) -> str | None:
        files = sorted(GEN_DIR.glob(f"{self.gen_prefix}_{task_id}_*.json"))
        for f in reversed(files):
            rec = json.loads(f.read_text())
            if rec.get("static_gates") == []:
                return rec["text"]
        return None

    def _save(self):
        self.state_path.write_text(json.dumps(self.state, indent=1))

    def assemble(self) -> str:
        return "\n\n".join(
            self.state["pieces"][tid]["code"]
            for tid in curriculum.TASK_IDS
            if tid in self.state["pieces"]) + "\n"


def main():
    import argparse
    from archagent.model import FrozenModel
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--harness-base", default="http://127.0.0.1:4190")
    ap.add_argument("--css", default="/tmp/harness-candidate.css")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--burst", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=360)
    ap.add_argument("--state", default=None)
    args = ap.parse_args()

    model = FrozenModel(threads=args.threads)
    builder = CSSBuilder(model, args.harness_base, Path(args.css),
                         state_path=Path(args.state) if args.state else None)
    ids = curriculum.TASK_IDS if args.tasks == "all" else args.tasks.split(",")
    for tid in ids:
        piece = builder.build_task(tid, burst=args.burst,
                                   max_tokens=args.max_tokens)
        if piece is None and tid in curriculum.TASK_IDS:
            # continue with other pieces; report at the end
            print(f"!! {tid} not accepted — continuing")
    print("\nusage:", model.usage())
    ok = [t for t in curriculum.TASK_IDS if t in builder.state["pieces"]]
    print(f"pieces accepted: {len(ok)}/{len(curriculum.TASK_IDS)}")
    css = builder.assemble()
    Path(args.css).write_text(css)
    print(f"assembled {len(css.splitlines())} css lines -> {args.css}")


if __name__ == "__main__":
    main()
