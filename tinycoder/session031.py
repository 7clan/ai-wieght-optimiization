"""Session031: Qwen0.5B self-repair architect for the DevMetrics dashboard.

The frozen 0.5B model writes every target module. Guided ONLY by the public
contract, its own previous attempt and public execution errors — zero teacher
bytes. Each repair round is scored, archived, and later deployed live by the
collector so every score is visible as an actual site. Model code executes
solely inside restricted, network-disabled, unprivileged Docker.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import MODEL_ID, _torch_model, docker_command
from .session015 import MODEL_PARAMETER_COUNT
from .session021 import generate_one
from .session027 import ROLE_PATHS, failure
from .session031_contract import (NAME, ROLES, PUBLIC, PREFIX, fingerprint,
                                   holdout, prompt)

IMAGE = "tinycoder-session031-selfrepair:1"
# Token ceilings raised after round 4 for truncation-prone roles (disclosed
# search-budget change; the contract itself stays frozen). Sixth amendment:
# ui 1900 -> 2400 after rounds 21-24 measured full-length ui candidates
# truncating exactly at the ceiling mid-JSX ("Unexpected end of file before a
# closing h1 tag"); anti-bloat anchors were added to the ui PUBLIC EXAMPLE
# so shorter components need less headroom.
LIMITS = {"logic": 320, "store": 1200, "api": 850, "ui": 2400, "css": 420}
BASE_SEED = 2026113100
WALL_BUDGET_SECONDS = 14400
# Measured finding: including the model's own Session030 api bytes in repair
# prompts caused old-name contamination (/api/items instead of /api/entries)
# across 8 rounds, so own-bytes memory excludes role "api".
SELF_MEMORY_EXCLUDE = ("api",)
ROLE_CHECKS = {"logic": ("logic_structured",),
               "store": ("persistence", "store_delete", "store_validation"),
               "api": ("health", "get", "post", "post_invalid", "delete",
                       "projects", "summary"),
               "ui": ("ui_wiring", "ui_offline"), "css": ()}
SELF_MEMORY_PATH = "experiments/session030_transfer_predictions.json"


def evaluate(modules, cases, phase, *, timeout=75):
    require_sandbox()
    if set(modules) != set(ROLES) or phase not in ("public", "holdout"):
        raise ValueError("Invalid evaluator request")
    with tempfile.TemporaryDirectory(prefix="qwen031-") as dirname:
        root = Path(dirname)
        inp, output = root / "input", root / "output"
        inp.mkdir(mode=0o755)
        output.mkdir(mode=0o777)
        os.chmod(root, 0o755)
        os.chmod(output, 0o777)
        req = inp / "input.json"
        req.write_text(json.dumps({"modules": modules, "cases": cases,
                                   "phase": phase}), encoding="utf8")
        os.chmod(req, 0o644)
        name = "qwen031-" + uuid.uuid4().hex[:12]
        try:
            proc = subprocess.run(docker_command(IMAGE, inp, output, name, is_web=True),
                                  capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           timeout=8, check=False)
            return failure(phase, "Bounded isolated Docker timeout")
        record = output / "result.json"
        if proc.returncode or not record.is_file():
            return failure(phase, "Isolated evaluator error: " + proc.stderr[-220:])
        result = json.loads(record.read_text(encoding="utf8"))
        if result.get("phase") != phase or set(result.get("modules", {})) != set(ROLES):
            raise RuntimeError("Evaluator identity mismatch")
        return result


def metric(report, role):
    entry = report["modules"][role]
    return (int(entry["passed"]),
            sum(bool(report["checks"].get(x)) for x in ROLE_CHECKS[role]),
            int(entry["syntax_valid"]))


def total_score(result):
    return (int(bool(result["integrated"])),
            sum(int(bool(result["modules"][r]["passed"])) for r in ROLES),
            int(result["completed_checks"]),
            sum(int(bool(result["modules"][r]["syntax_valid"])) for r in ROLES))


def snapshot(round_, modules, public, elapsed, tokens):
    return {"round": round_,
            "modules": dict(modules),
            "modules_sha256": {r: hashlib.sha256(modules[r].encode()).hexdigest()
                               for r in ROLES},
            "public": {"integrated": public["integrated"],
                       "passed": {r: public["modules"][r]["passed"] for r in ROLES},
                       "checks": dict(public["checks"]),
                       "completed_checks": public["completed_checks"],
                       "failure_reasons": list(public.get("failure_reasons", []))},
            "elapsed_seconds": round(elapsed, 1), "output_tokens": tokens}


def load_state(path: Path):
    state = json.loads(path.read_text(encoding="utf8"))
    for key in ("round", "selected", "baseline", "public", "attempts", "tokens",
                "elapsed", "rounds"):
        if key not in state:
            raise ValueError("Incomplete resume state: " + key)
    if set(state["selected"]) != set(ROLES) or set(state["baseline"]) != set(ROLES):
        raise ValueError("Corrupt resume state modules")
    return state


def load_self_memory(path: str):
    """Own-bytes memory: modules the SAME frozen model wrote and that passed
    an independent holdout in Session030. Never teacher or human code."""
    memory = {}
    try:
        prior = json.loads(Path(path).read_text(encoding="utf8"))
        report_path = Path("experiments/session030_transfer_report.json")
        report = (json.loads(report_path.read_text(encoding="utf8"))
                  if report_path.is_file() else {})
        passed = {r: v.get("passed") for r, v in
                  report.get("guided", {}).get("holdout", {}).get("modules", {}).items()}
        for role, source in (prior.get("selected") or {}).items():
            if passed.get(role) and role in ROLES and role not in SELF_MEMORY_EXCLUDE:
                memory[role] = source
    except (OSError, ValueError):
        return {}
    return memory


def run(args):
    require_sandbox()
    root = Path(args.output_dir)
    state_path = Path(args.state)
    started = time.monotonic()
    if args.resume:
        if not state_path.is_file() and not (root / "state.json").is_file():
            raise FileNotFoundError("Nothing to resume: no prior state file")
        state = load_state(state_path if state_path.is_file() else root / "state.json")
        baseline = state["baseline"]
        selected = state["selected"]
        public = state["public"]
        attempts = state["attempts"]
        rounds = state["rounds"]
        tokens = state["tokens"]
        elapsed0 = state["elapsed"]
        print(json.dumps({"resumed_from_round": state["round"],
                          "attempts_so_far": len(attempts)}), flush=True)
    else:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError("Prior output exists")
        baseline, selected, public = {}, {}, None
        attempts, rounds, tokens, elapsed0 = [], [], 0, 0.0
    root.mkdir(parents=True, exist_ok=True)

    model, tokenizer = _torch_model()
    count = sum(p.numel() for p in model.parameters())
    if count != MODEL_PARAMETER_COUNT:
        raise RuntimeError("Unexpected student model capacity")

    if public is None:
        # Round 0: untouched greedy baseline, one completion per role.
        for i, role in enumerate(ROLES):
            head = prompt(role)
            raw, n = generate_one(model, tokenizer, head, max_tokens=LIMITS[role],
                                  seed=BASE_SEED + i, stochastic=False)
            baseline[role] = PREFIX[role] + raw
            attempts.append({"stage": "baseline", "round": 0, "role": role,
                             "prompt": head, "raw": raw, "output_tokens": n,
                             "accepted": True})
            tokens += n
            print(json.dumps({"baseline": role, "tokens": n}), flush=True)
        selected = dict(baseline)
        public = evaluate(baseline, PUBLIC, "public")
        baseline_public = public
        elapsed = elapsed0 + (time.monotonic() - started)
        rounds.append(snapshot(0, selected, public, elapsed, tokens))
        print(json.dumps({"round": 0, "score": total_score(public),
                          "passed": {r: public["modules"][r]["passed"] for r in ROLES}}),
              flush=True)
    else:
        elapsed = elapsed0
        baseline_public = state.get("baseline_public")
        if baseline_public is None:
            baseline_public = evaluate(baseline, PUBLIC, "public")

    last_try = {}
    self_memory = load_self_memory(SELF_MEMORY_PATH) if args.self_memory else {}
    if self_memory:
        print(json.dumps({"self_memory_roles": sorted(self_memory)}), flush=True)
    next_round = (rounds[-1]["round"] + 1) if rounds else 1
    for round_ in range(next_round, args.rounds + 1):
        if all(public["modules"][r]["passed"] for r in ROLES):
            print(json.dumps({"early_stop": "all public checks pass",
                              "round": round_ - 1}), flush=True)
            break
        if elapsed > args.wall_budget:
            print(json.dumps({"wall_budget_reached": True, "round": round_}), flush=True)
            break
        for i, role in enumerate(ROLES):
            if public["modules"][role]["passed"]:
                last_try.pop(role, None)
                continue
            # The model's most recent own output for this role, accepted or not:
            # rejected candidates are still the model's previous attempt, and
            # their execution error is the freshest feedback it can receive.
            recent = last_try.get(role)
            if recent is not None:
                previous_src, previous_err = recent
            else:
                previous_src = selected[role]
                previous_err = public["modules"][role]["error"] or "Public contract failed"
            own_example = self_memory.get(role, "")
            # Sixth amendment: every candidate now carries the full feedback
            # prompt (previous attempt, evaluator errors, failing-position
            # quote). Blind resamples are retired after 0 accepts in 48
            # post-round-16 tries; different seeds still give stochastic
            # variety across the three feedback candidates.
            head_fb = prompt(role, error=previous_err, previous=previous_src,
                             own_example=own_example)
            candidates = (
                ("feedback-repair", head_fb,
                 BASE_SEED + 1000 + round_ * 100 + i),
                ("feedback-repair-2", head_fb,
                 BASE_SEED + 2000 + round_ * 100 + i),
                ("feedback-repair-3", head_fb,
                 BASE_SEED + 3000 + round_ * 100 + i),
            )
            for stage, head, seed in candidates:
                raw, n = generate_one(model, tokenizer, head, max_tokens=LIMITS[role],
                                      seed=seed, stochastic=True)
                tokens += n
                challenger = dict(selected)
                challenger[role] = PREFIX[role] + raw
                result = evaluate(challenger, PUBLIC, "public")
                accepted = metric(result, role) > metric(public, role)
                last_try[role] = (challenger[role],
                                  result["modules"][role]["error"]
                                  or "Public contract failed")
                attempts.append({"stage": stage, "round": round_, "role": role,
                                 "prompt": head, "raw": raw, "output_tokens": n,
                                 "accepted": accepted,
                                 "public_result": result["modules"][role],
                                 "candidate_source": challenger[role]})
                print(json.dumps({"round": round_, "role": role, "stage": stage,
                                  "tokens": n, "passed": result["modules"][role]["passed"],
                                  "accepted": accepted,
                                  "error": result["modules"][role]["error"]}), flush=True)
                if accepted:
                    selected, public = challenger, result
                    last_try.pop(role, None)
                    break
        elapsed = elapsed0 + (time.monotonic() - started)
        rounds.append(snapshot(round_, selected, public, elapsed, tokens))
        save_json(root / "state.json",
                  {"round": round_, "selected": selected, "baseline": baseline,
                   "baseline_public": baseline_public, "public": public,
                   "attempts": attempts, "tokens": tokens,
                   "elapsed": elapsed, "rounds": rounds})
        print(json.dumps({"round": round_, "score": total_score(public),
                          "passed": {r: public["modules"][r]["passed"] for r in ROLES},
                          "tokens": tokens, "elapsed": round(elapsed, 1)}), flush=True)

    del model
    gc.collect()
    # Protected holdout is first accessed here, after every public choice froze.
    holdout_cases = holdout()
    baseline_hold = evaluate(baseline, holdout_cases, "holdout")
    final_hold = evaluate(selected, holdout_cases, "holdout")
    final_public = evaluate(selected, PUBLIC, "public")
    elapsed = elapsed0 + (time.monotonic() - started)
    report = {"session": "031", "status": "completed", "model": MODEL_ID,
              "parameter_count": count, "training_steps": 0, "weight_edits": 0,
              "new_application": NAME, "contract_sha256": fingerprint(),
              "target_app_modules_from_qwen": list(ROLES),
              "teacher_bytes": 0, "teacher_supplied_anything": False,
              "self_repair_only": True, "self_repair_rounds": len(rounds) - 1,
              "own_prior_session_bytes_in_prompts": sorted(self_memory),
              "permanent_weight_learning": False,
              "trusted_scaffold": ["file signatures/imports", "evaluation runtime",
                                   "React runtime", "deployment gallery"],
              "baseline": {"public": baseline_public,
                           "holdout": baseline_hold},
              "final": {"public": final_public, "holdout": final_hold},
              "rounds": [{k: v for k, v in snap.items() if k != "modules"}
                         for snap in rounds],
              "search": {"candidate_count": len(attempts), "output_tokens": tokens,
                         "wall_seconds": round(elapsed, 2),
                         "max_rounds": args.rounds,
                         "wall_budget_seconds": args.wall_budget,
                         "private_holdout_seen_during_selection": False},
              "ui_behavior_verified_in_jsdom": bool(final_public["checks"].get("ui_offline")),
              "ui_browser_clicks_verified": False,
              "production_ready": False}
    save_json(root / "report.json", report)
    save_json(root / "predictions.json",
              {"greedy": baseline, "selected": selected, "attempts": attempts,
               "rounds": rounds,
               "source_sha256": {r: hashlib.sha256(selected[r].encode()).hexdigest()
                                 for r in ROLES}})
    save_json(root / "state.json",
              {"round": rounds[-1]["round"] if rounds else 0, "selected": selected,
               "baseline": baseline, "baseline_public": baseline_public,
               "public": public, "attempts": attempts,
               "tokens": tokens, "elapsed": elapsed, "rounds": rounds})
    for role, path in ROLE_PATHS.items():
        target = root / "generated" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(selected[role], encoding="utf8")
    print(json.dumps({"baseline_holdout": baseline_hold["integrated"],
                      "final_holdout": final_hold["integrated"],
                      "baseline_passes": {r: baseline_hold["modules"][r]["passed"] for r in ROLES},
                      "final_passes": {r: final_hold["modules"][r]["passed"] for r in ROLES},
                      "rounds": len(rounds) - 1, "candidates": len(attempts)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/session031")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--self-memory", action="store_true",
                        help="Prompt with the model's own verified prior-session bytes")
    parser.add_argument("--state", default="experiments/session031_selfrepair_state.json")
    parser.add_argument("--wall-budget", type=float, default=WALL_BUDGET_SECONDS,
                        help="Cumulative wall-clock budget in seconds")
    args = parser.parse_args()
    if args.rounds < 0 or args.rounds > 32:
        raise ValueError("rounds must be within 0..32")
    run(args)


if __name__ == "__main__":
    main()
