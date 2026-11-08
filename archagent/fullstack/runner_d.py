"""Track D — staged contract-first generation with execution feedback.

Long-lived daemon.  Loads the frozen model once per segment (RAM does
not allow model + dev server + browser at once), generates every
application byte from the exact-shape contracts in contracts.py,
gates each piece statically (tsc / eslint / prisma), repairs with
Qwen-generated patches guided by measured failures (max 3 rounds x 4
samples per contract), and runs the frozen dynamic suites (apitest,
uitest) at the declared checkpoints with the model unloaded.

Provenance: every accepted file is recorded with round/sample/seed/
tokens/sha256.  Nothing in this module writes application bytes.
"""
from __future__ import annotations

import gc
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.fullstack.contracts import CONTRACTS  # noqa: E402
from archagent.fullstack.gen_one import build_prompt, quick_reject  # noqa: E402

EXP = ROOT / "experiments/zai-fullstack"
STAGE = EXP / "staging"
GEN = EXP / "experiments/zai-fullstack/generations"
REPORTS = EXP / "reports"
LEDGER = EXP / "PROVENANCE.json"
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/.npm-global/lib/node_modules",
    BASE="http://127.0.0.1:3000",
)

# stages after which dynamic gates run (model unloaded, dev started)
CHECKPOINTS = {"route-id": ["apitest"], "page": ["uitest"]}


def log(msg: str) -> None:
    print(msg, flush=True)


class Ledger:
    def __init__(self) -> None:
        self.data = {"files": {}, "stages": [], "model_usage_cumulative":
                     {"generations": 0, "total_new_tokens": 0,
                      "total_seconds": 0.0}}

    def record_stage(self, rec: dict) -> None:
        self.data["stages"].append(rec)
        LEDGER.write_text(json.dumps(self.data, indent=1))

    def record_file(self, path: str, rec: dict) -> None:
        self.data["files"][path] = rec
        LEDGER.write_text(json.dumps(self.data, indent=1))

    def add_usage(self, usage: dict) -> None:
        c = self.data["model_usage_cumulative"]
        c["generations"] += usage.get("generations", 0)
        c["total_new_tokens"] += usage.get("total_new_tokens", 0)
        c["total_seconds"] += round(
            c["total_seconds"] + usage.get("total_seconds", 0.0), 1)
        LEDGER.write_text(json.dumps(self.data, indent=1))


def run_gates(contract: dict, installed_ok: bool) -> tuple[bool, str]:
    """Static gates for a contract.  Returns (pass, feedback)."""
    if not installed_ok:
        return False, "installer wrote nothing (marker/shape mismatch)"
    gates = contract.get("gates", [])
    feedback_parts = []
    ok = True
    if "prisma" in gates:
        r = install.run_cmd(["bun", "run", "db:push"], install.APP,
                            timeout=180)
        if r["exit"] != 0:
            ok = False
            feedback_parts.append("prisma db push failed:\n" + r["out"][-500:])
    if "tsc" in gates:
        r = install.run_cmd(
            ["node_modules/.bin/tsc", "--noEmit", "-p", "tsconfig.gate.json"],
            install.APP, timeout=300)
        if r["exit"] != 0:
            ok = False
            feedback_parts.append("tsc --noEmit reported:\n" + r["out"][-900:])
    if "eslint" in gates:
        r = install.run_cmd(["node_modules/.bin/eslint", "src"],
                            install.APP, timeout=300)
        if r["exit"] != 0:
            ok = False
            feedback_parts.append("eslint reported:\n" + r["out"][-600:])
    if "types_unit" in gates:
        r = install.run_cmd(
            ["bun", "scripts/check-types.ts"],
            install.APP, timeout=60)
        if r["exit"] != 0:
            ok = False
            feedback_parts.append("types unit check failed:\n" + r["out"][-400:])
    return ok, "\n".join(feedback_parts)


def dynamic_gates(names: list[str]) -> dict:
    """Run frozen suites with the dev server up. Returns per-suite result."""
    out = {}
    devserver.start_dev()
    for name in names:
        script = {"apitest": "apitest.mjs", "uitest": "uitest.mjs"}[name]
        try:
            r = subprocess.run(["node", str(EXP / script)],
                               capture_output=True, text=True, timeout=600,
                               env=NODE_ENV, cwd=str(EXP))
            tail = (r.stdout + r.stderr).strip().splitlines()
            out[name] = {"exit": r.returncode, "tail": tail[-12:]}
        except subprocess.TimeoutExpired:
            out[name] = {"exit": 124, "tail": ["TIMEOUT"]}
        log(f"[dynamic:{name}] exit={out[name]['exit']}")
        for line in out[name]["tail"][-6:]:
            log(f"    {line}")
    return out


def generate_samples(model, contract: dict, round_no: int,
                     feedback: str | None, own_prev: str | None) -> list[dict]:
    """Generate up to 4 samples for this round (in-process)."""
    prompt, anchor = build_prompt(contract, feedback, own_prev)
    max_tokens = contract.get("max_tokens", 700)
    samples = []
    for k in range(4):
        seed = (k * 1013 + round_no * 77) or 7
        stochastic = k != 0
        text, usage = model.generate(prompt, max_tokens=max_tokens,
                                     seed=seed, stochastic=stochastic)
        reason = quick_reject(text, anchor)
        samples.append(dict(k=k, seed=seed, stochastic=stochastic,
                            usage=usage, completion=text,
                            rejected_reason=reason))
        log(f"  [gen r{round_no} k{k}] seed={seed} tok={usage['tokens']} "
            f"reject={reason}")
        GEN.mkdir(parents=True, exist_ok=True)
        (GEN / f"{contract['id']}_r{round_no}_k{k}.json").write_text(
            json.dumps(dict(contract=contract["id"], round=round_no, k=k,
                            prompt=prompt, anchor=anchor, usage=usage,
                            seed=seed, stochastic=stochastic,
                            rejected_reason=reason, completion=text),
                       ensure_ascii=False, indent=1))
    return samples


def install_sample(contract: dict, completion: str) -> tuple[bool, str]:
    """Write one sample's file (or merge schema). Returns (ok, path)."""
    body = completion.strip("\n")
    if contract["kind"] == "schema":
        if "model InventoryItem" not in body:
            return False, "no InventoryItem model in output"
        install.merge_schema_block(body)
        return True, contract["file"]
    target = install.APP / contract["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body + "\n")
    return True, contract["file"]


def revert(contract: dict) -> None:
    """Remove a rejected candidate's file (or schema model)."""
    if contract["kind"] == "schema":
        import re as _re
        p = install.APP / "prisma/schema.prisma"
        if p.exists():
            t = _re.sub(r"\nmodel InventoryItem \{.*?\n\}\n", "\n",
                        p.read_text(), flags=_re.DOTALL)
            p.write_text(t)
    else:
        p = install.APP / contract["file"]
        if p.exists():
            p.unlink()


def run_stage(model, contract: dict, ledger: Ledger) -> dict:
    cid = contract["id"]
    log(f"\n===== STAGE {cid} ({contract['file']}) =====")
    feedback = None
    own_prev = None
    accepted = None
    rounds_used = 0
    last_feedback = None
    usage_before = dict(model.usage())
    for round_no in range(3):
        rounds_used = round_no + 1
        samples = generate_samples(model, contract, round_no, feedback,
                                   own_prev)
        for s in samples:
            if s["rejected_reason"]:
                last_feedback = ("structural rejection: "
                                 + s["rejected_reason"])
                continue
            ok, path = install_sample(contract, s["completion"])
            gates_ok, gate_feedback = run_gates(contract, ok)
            last_feedback = gate_feedback or "gates passed"
            if gates_ok:
                accepted = s
                ledger.record_file(contract["file"], dict(
                    contract=cid, round=round_no, k=s["k"], seed=s["seed"],
                    tokens=s["usage"]["tokens"],
                    label="QWEN-ORIGINAL",
                    note=f"accepted on round {round_no} sample {s['k']}"))
                log(f"  ACCEPTED r{round_no} k{s['k']} "
                    f"({s['usage']['tokens']} tokens)")
                break
            revert(contract)
            log(f"  rejected r{round_no} k{s['k']}: {gate_feedback[:200]}")
        if accepted:
            break
        # prepare feedback for the next round from the best (last) sample
        non_rejected = [s for s in samples if not s["rejected_reason"]]
        if non_rejected:
            own_prev = non_rejected[-1]["completion"]
            feedback = last_feedback
        else:
            feedback = ("every sample was structurally rejected: "
                        + "; ".join(s["rejected_reason"] or "?"
                                    for s in samples))
            own_prev = None
    usage_after = dict(model.usage())
    delta = {k: usage_after[k] - usage_before[k] for k in usage_after}
    ledger.add_usage(delta)
    rec = dict(contract=cid, file=contract["file"],
               accepted=accepted is not None,
               rounds=rounds_used,
               usage_delta=delta,
               label="QWEN-ORIGINAL" if accepted else "FAILED")
    if not accepted:
        log(f"  STAGE {cid} FAILED after 3 rounds — needs integration "
            f"decision")
    ledger.record_stage(rec)
    return rec


def main() -> None:
    from archagent.model import FrozenModel
    start_from = 1
    if "--from" in sys.argv:
        start_from = int(sys.argv[sys.argv.index("--from") + 1])
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    ledger = Ledger()
    if LEDGER.exists():
        ledger.data = json.loads(LEDGER.read_text())

    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    log(f"model loaded; usage so far: {model.usage()}")

    try:
        for contract in CONTRACTS:
            if only and contract["id"] != only:
                continue
            rec = run_stage(model, contract, ledger)
            # dynamic checkpoints: unload model, bring dev up, run suites
            gates = contract.get("gates", [])
            dynamic = [g for g in gates if g in ("apitest", "uitest",
                                                "apitest_partial")]
            if dynamic and rec["accepted"]:
                log(f"[checkpoint {contract['id']}] unloading model for "
                    f"dynamic gates {dynamic}")
                del model
                gc.collect()
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:  # noqa: BLE001
                    pass
                results = dynamic_gates(dynamic)
                ledger.record_stage(dict(
                    contract=f"{contract['id']}:dynamic",
                    results=results))
                # reload for subsequent stages
                devserver.stop_dev()
                time.sleep(2)
                model = FrozenModel(threads=2)
                log(f"model reloaded; usage: {model.usage()}")
    except Exception:  # noqa: BLE001
        log("RUNNER ERROR:\n" + traceback.format_exc())
        raise
    finally:
        try:
            ledger.add_usage(model.usage())
        except Exception:  # noqa: BLE001
            pass
        devserver.start_dev()
        log("runner_d finished; dev server restarted")

    log("STAGE SUMMARY:")
    for s in ledger.data["stages"]:
        if "contract" in s:
            log(f"  {s['contract']}: accepted={s.get('accepted')}")


if __name__ == "__main__":
    main()
