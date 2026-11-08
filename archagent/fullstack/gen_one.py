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
             "pet-", "Pet "]


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
    """Cheap structural rejections before any gate runs."""
    if not completion.strip():
        return "empty completion"
    low = completion
    for w in DEMO_ECHO:
        if w in low:
            return f"demo echo: contains {w!r}"
    if len(completion.strip()) < 40:
        return "degenerate: too short"
    # crude brace balance (tsc gate does the real check)
    depth = 0
    in_str = None
    i = 0
    while i < len(completion):
        c = completion[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < len(completion) and completion[i + 1] == "/":
            i = completion.find("\n", i)
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
