"""One generation burst for one contract (subprocess, RAM-isolated).

Loads the frozen model, generates up to 4 samples for the given
contract (round 0 = first attempt; rounds 1-2 carry execution feedback
from the previous round), writes every sample — accepted or rejected —
with full prompt + completion + seed + tokens to the staging area,
then exits so the orchestrator can restart the dev server and gate the
code without the model resident in RAM.

Session-034 conventions: first sample of each round is greedy, then
sampled (temperature 0.72, top-p 0.93); seed = k*1013 + round*77.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver  # noqa: E402
from archagent.fullstack.contracts import CONTRACTS  # noqa: E402
from archagent.fullstack.prompts import CONCEPT  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402

STAGE = ROOT / "experiments/zai-fullstack/staging"
GEN = ROOT / "experiments/zai-fullstack/generations"

# Demo-domain vocabulary: any completion containing these is a demo
# echo (the pet-shelter example leaked into target code) -> rejected.
DEMO_ECHO = ["Adoption", "adoption", "species", "shelter", "Shelter",
             "pet-", "Pet ", "HealthStatus", "healthOf", "HealthRecord",
             "CareLevel", "careLevelOf", "Animal", "useAnimals",
             "saveAnimal", "/api/animals", "book", "Book", "library"]


def _looks_like_prose(line: str) -> bool:
    """Heuristic: natural-language line (spec echo / instruction
    paraphrase) rather than code.  Prose = >= 4 words, only letters,
    digits and , . : ; - ' ( ) spaces — no code punctuation."""
    s = line.strip()
    if len(s) < 8:
        return False
    words = s.split()
    if len(words) < 3:
        return False
    import re as _re
    return bool(_re.fullmatch(r"[A-Za-z0-9 ,.:;'\-/\u2019()]+", s))


# High-specificity prompt-scaffolding markers: these strings only ever
# appear in the harness prompt structure, never in legitimate code.
_PROMPT_MARKERS = [
    "tsc --noEmit reported:",
    "eslint reported:",
    "The automated checks reported:",
    "Your previous attempt",
    "Write the complete file now",
    "Now YOUR task",
    "Example from a DIFFERENT app",
    "The first line is already written",
    "Fix exactly that.",
    "you already have",
]


def _is_prose_fragment(s: str) -> bool:
    """Any line made only of prose characters (even 1-2 words) —
    trailing continuation fragments like 'error.' must not block the
    trailing strip."""
    import re as _re
    return bool(_re.fullmatch(r"[A-Za-z0-9 ,.:;'\-/\u2019()]+", s.strip()))


def strip_prompt_echo(text: str, prompt: str) -> str:
    """Remove prompt-echo regions (harness bug #4 fix).

    The model frequently appends verbatim chunks of its own prompt
    (feedback blocks, spec bullets, instruction sentences) after
    otherwise-valid code.  Two-phase mechanical strip:
    1. CUT at the first mid-file line containing a distinctive
       prompt-scaffolding marker (feedback echo, instruction echo);
    2. From the end, drop blank / verbatim-prompt / prose-like lines.
    (Session-034 strip_prose successor; calibrated on real samples.)
    """
    # phase 1: marker cut
    lines = text.splitlines()
    cut_at = None
    for idx, line in enumerate(lines):
        if idx == 0:
            continue  # the anchor's own first line never counts
        for marker in _PROMPT_MARKERS:
            if marker in line:
                cut_at = idx
                break
        if cut_at is not None:
            break
    if cut_at is not None:
        lines = lines[:cut_at]
    # phase 2: mid-file pure-prose region removal (blank-line-bounded
    # runs where >=70% of lines look like prose and none carry code
    # punctuation beyond the prose-allowed set)
    regions = []
    cur: list[str] = []
    for line in lines:
        if line.strip() == "":
            if cur:
                regions.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        regions.append(cur)
    kept_regions = []
    for region in regions:
        prose_lines = sum(1 for ln in region if _looks_like_prose(ln))
        has_code_punct = any(
            any(ch in ln for ch in "{}=<>") for ln in region)
        is_prose_region = (prose_lines / len(region) >= 0.7
                           and not has_code_punct)
        if not is_prose_region:
            kept_regions.append(region)
    lines = []
    for region in kept_regions:
        if lines:
            lines.append("")
        lines.extend(region)
    # phase 3: trailing strip
    popped = 0
    while lines and popped < 200:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            popped += 1
            continue
        if (len(last) >= 8 and last in prompt
                and _is_prose_fragment(last)):
            lines.pop()
            popped += 1
            continue
        if _looks_like_prose(last) or _is_prose_fragment(last):
            lines.pop()
            popped += 1
            continue
        break
    return "\n".join(lines)


def trim_to_exports(text: str, required: list[str]) -> str:
    """Mechanical file trim (Session-034 cut_trailing_prose successor).

    Keeps the leading prefix (imports, 'use client') and the top-level
    export segments whose names are in `required`, in order; drops
    everything after the last required export (trailing echoes,
    duplicated blocks, prose).  Purely structural — no code is written
    or modified by this function.
    """
    import re as _re
    # scan for top-level 'export <kind> <name>' positions
    segs: list[tuple[int, str]] = []
    depth = 0
    in_str = None
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                break
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                break
            i = j + 1
        elif c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        elif (depth == 0 and (text.startswith("export ", i)
                              or text.startswith("'use client'", i))):
            m = _re.match(
                r"export\s+(?:default\s+)?(?:async\s+)?"
                r"(?:function|interface|type|class|const|let|var|enum)\s"
                r"+(\w+)", text[i:])
            if m:
                segs.append((i, m.group(1)))
        i += 1
    if not segs or not required:
        return text
    prefix = text[:segs[0][0]]
    pieces = [prefix]
    kept = 0
    for idx, (start, name) in enumerate(segs):
        if name not in required:
            continue
        kept += 1
        if idx + 1 < len(segs):
            nxt = segs[idx + 1][0]
        else:
            nxt = _balanced_end(text, start)
        pieces.append(text[start:nxt].rstrip() + "\n\n")
    if kept == 0:
        return text
    return "".join(pieces).rstrip() + "\n"


def _balanced_end(text: str, start: int) -> int:
    """End position (exclusive) of the top-level construct at `start`.

    Only CURLY BRACES define the construct body (harness bug #3: the
    first version also counted the signature's parentheses, so every
    function was truncated at `): ReturnType {`).  Type aliases without
    braces end at the first line not continuing a union.
    """
    depth = 0
    paren = 0  # () and [] nesting — EOL heuristic must not fire
    # inside multi-line signatures or array literals (harness bug #3b)
    in_str = None
    i = start
    n = len(text)
    seen_brace = False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            if j == -1:
                return n
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                return n
            i = j + 1
        elif c in "( [".replace(" ", ""):
            paren += 1
        elif c in ") ]".replace(" ", ""):
            paren -= 1
        elif c == "{":
            depth += 1
            seen_brace = True
        elif c == "}":
            depth -= 1
            if seen_brace and depth == 0:
                j = text.find("\n", i)
                return n if j == -1 else j + 1
        elif (not seen_brace and paren == 0 and c == "\n"):
            nxt = text[i + 1:].lstrip() if i + 1 < n else ""
            if not nxt.startswith("|") and not nxt.startswith("&"):
                return i + 1
        i += 1
    return n


def build_prompt(contract: dict, feedback: str | None,
                 own_prev: str | None) -> tuple[str, str]:
    parts = [CONCEPT, "", contract["demo"], ""]
    parts.append("Now YOUR task.  Write the file "
                 f"{contract['file']} for the inventory application.")
    parts.append("")
    parts.append(contract["spec"])
    if own_prev:
        parts.append("")
        parts.append("Your previous attempt (which failed the checks) was:")
        parts.append(own_prev[-1500:])
    if feedback:
        parts.append("")
        parts.append("The automated checks reported:")
        parts.append(feedback[-1200:])
        parts.append("Fix exactly that.")
    parts.append("")
    parts.append("Write the complete file now.  The first line is "
                 "already written; continue from it:")
    parts.append(contract["anchor"])
    return "\n".join(parts), contract["anchor"]


def quick_reject(completion: str, anchor: str) -> str | None:
    """Cheap structural rejections before any gate runs.

    Brace balance is checked on ANCHOR + completion (the anchor opens
    blocks the completion closes) — the completion alone would always
    look unbalanced.  (Harness bug #1 of Session 035, fixed with full
    disclosure: three valid schema samples were wrongly rejected
    before this fix.)
    """
    if not completion.strip():
        return "empty completion"
    for w in DEMO_ECHO:
        if w in completion:
            return f"demo echo: contains {w!r}"
    if len(completion.strip()) < 40:
        return "degenerate: too short"
    text = anchor + "\n" + completion
    depth = 0
    in_str = None
    i = 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            i = text.find("\n", i)
            if i == -1:
                break
        elif c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
            if depth < 0:
                return "unbalanced brackets (closes too early)"
        i += 1
    if depth > 0:
        return f"unbalanced brackets ({depth} unclosed)"
    return None


def main() -> None:
    args = sys.argv[1:]
    cid = args[0]
    round_no = int(args[args.index("--round") + 1]) if "--round" in args else 0
    feedback = None
    own_prev = None
    if "--feedback" in args:
        p = Path(args[args.index("--feedback") + 1])
        feedback = p.read_text() if p.exists() else None
    if "--prev" in args:
        p = Path(args[args.index("--prev") + 1])
        own_prev = p.read_text() if p.exists() else None

    contract = next(c for c in CONTRACTS if c["id"] == cid)
    prompt, anchor = build_prompt(contract, feedback, own_prev)
    out_dir = STAGE / cid / f"round{round_no}"
    out_dir.mkdir(parents=True, exist_ok=True)

    devserver.stop_dev()
    time.sleep(1)
    model = FrozenModel(threads=2)
    max_tokens = contract.get("max_tokens", 700)

    manifest = []
    for k in range(4):
        seed = (k * 1013 + round_no * 77) or 7
        stochastic = k != 0
        t0 = time.time()
        text, usage = model.generate(prompt, max_tokens=max_tokens,
                                     seed=seed, stochastic=stochastic)
        reason = quick_reject(text, anchor)
        sample = dict(
            contract=cid, round=round_no, k=k, seed=seed,
            stochastic=stochastic, usage=usage,
            wall=round(time.time() - t0, 1),
            rejected_reason=reason,
            completion=text,
        )
        (out_dir / f"sample_{k}.json").write_text(
            json.dumps(sample, ensure_ascii=False, indent=1))
        # full permanent archive too
        GEN.mkdir(parents=True, exist_ok=True)
        (GEN / f"{cid}_r{round_no}_k{k}.json").write_text(
            json.dumps(dict(**sample, prompt=prompt, anchor=anchor),
                       ensure_ascii=False, indent=1))
        manifest.append({kk: sample[kk] for kk in
                         ("k", "seed", "usage", "rejected_reason")})
        print(f"[{cid} r{round_no} k{k}] seed={seed} "
              f"tok={usage['tokens']} reject={reason}", flush=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(model.usage()), "DONE")


if __name__ == "__main__":
    main()
