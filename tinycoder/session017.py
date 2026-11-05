"""Session017: contract-first full-stack vertical slices with Qwen0.5B.

Frozen ten authored tasks, three modules each (Python / Express / React).
Greedy untouched model vs exactly one adaptive sample and one repair per
initially failed module. All generated code runs ONLY in restricted Docker.
Public cases guide selection. Holdout cases are loaded after search finishes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gc
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import _torch_model, docker_command, MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session017_contracts import (MODULES, contract_sha256, contracts,
                                   holdout_cases, module_prompt)
from .session017_scaffold import export_project


DOCKER_IMAGE = "tinycoder-session017-fullstack:1"
NEW_TOKENS = 180


def _failure_result(task_id, message):
    return {"task_id": task_id, "passed": False, "syntax_valid": False,
            "failure_bin": "unclassified_logic_gap", "error": message,
            "modules": {k: {"passed": False, "syntax_valid": False,
                             "error": message} for k in MODULES},
            "integration": {"passed": False, "error": message}}


def _one_docker(task, modules, cases, *, timeout=25):
    """One potentially malicious generated app per restricted Docker run."""
    require_sandbox()
    with tempfile.TemporaryDirectory(prefix="session017_") as directory:
        root = Path(directory)
        src, dst = root / "in", root / "out"
        src.mkdir(mode=0o755)
        dst.mkdir(mode=0o777)
        os.chmod(root, 0o755)
        os.chmod(dst, 0o777)
        data = src / "input.json"
        data.write_text(json.dumps({"task": {"task_id": task["task_id"],
                                             "contract": task["contract"]},
                                    "modules": modules, "cases": cases}), encoding="utf-8")
        os.chmod(data, 0o644)
        name = "tinycoder-s017-" + uuid.uuid4().hex[:14]
        cmd = docker_command(DOCKER_IMAGE, src, dst, name, True)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           text=True, timeout=10, check=False)
            return _failure_result(task["task_id"], f"Docker timeout {timeout}s")
        if proc.returncode or not (dst / "result.json").exists():
            return _failure_result(task["task_id"],
                                   "Docker evaluator error: " + proc.stderr[-250:])
        record = json.loads((dst / "result.json").read_text(encoding="utf-8"))
        if record.get("task_id") != task["task_id"]:
            raise RuntimeError("Docker evaluator changed task identity")
        return record


def check_apps(tasks, solutions, cases, *, workers=3):
    require_sandbox()
    if len(tasks) != len({t["task_id"] for t in tasks}):
        raise ValueError("Duplicate app identities")
    if any(t["task_id"] not in solutions or t["task_id"] not in cases for t in tasks):
        raise ValueError("Mismatched application inputs")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda t: _one_docker(t, solutions[t["task_id"]],
                                                  cases[t["task_id"]]), tasks))


def generate(model, tokenizer, prompts, *, seed, stochastic, batch_size=4):
    """Only frozen base-model inference; do_sample is optional, never gradients."""
    import torch
    if not prompts:
        return {}, 0
    torch.manual_seed(seed)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokens = 0
    completions = {}
    pairs = list(prompts.items())
    for start in range(0, len(pairs), batch_size):
        chunk = pairs[start:start + batch_size]
        ids, strings = zip(*chunk)
        encoded = tokenizer(list(strings), padding=True,
                            return_tensors="pt", add_special_tokens=False)
        options = {"do_sample": stochastic, "max_new_tokens": NEW_TOKENS,
                   "pad_token_id": tokenizer.pad_token_id}
        if stochastic:
            options["temperature"] = 0.7
        with torch.inference_mode():
            result = model.generate(**encoded, **options)
        continuation = result[:, encoded["input_ids"].shape[1]:]
        decoded = tokenizer.batch_decode(continuation, skip_special_tokens=True)
        completions.update(zip(ids, decoded, strict=True))
        tokens += sum(int((row != tokenizer.pad_token_id).sum().item())
                      for row in continuation)
    return completions, tokens


def _prompts(tasks, roles):
    return {(task["task_id"], role): module_prompt(task, role)
            for task in tasks for role in roles}


def _assembled(task, continuations):
    return {role: module_prompt(task, role) + continuations[(task["task_id"], role)]
            for role in MODULES}


def choose_roles(tasks, records):
    """Modify only modules with public failures; prioritize typed defects."""
    by_id = {r["task_id"]: r for r in records}
    selected = []
    for task in tasks:
        result = by_id[task["task_id"]]
        if result["passed"]:
            continue
        failed = [role for role in MODULES if not result["modules"][role]["passed"]]
        if not failed:
            failed = ["api"]  # Integration-only failure: try the boundary.
        selected.extend((task["task_id"], role) for role in failed)
    return selected


def score(result):
    """Public checks cannot score held-out cases by construction."""
    return (int(result["passed"]),
            sum(bool(result["modules"][r]["passed"]) for r in MODULES),
            sum(bool(result["modules"][r]["syntax_valid"]) for r in MODULES))


def make_repair_prompt(task, role, prior, diagnostic):
    reason = str(diagnostic.get("error") or "public contract check failed")
    reason = reason.replace("\n", " ")[:170]
    previous = prior[:800]
    if role == "logic":
        prefix = (f"# Previous implementation failed its public checks: {reason}\n"
                  + "\n".join("# " + line for line in previous.splitlines()[:16]) + "\n")
    else:
        prefix = f"/* Previous {role} failed public checks: {reason}\n{previous}\n*/\n"
    return prefix + module_prompt(task, role)


def metrics(records):
    n = len(records)
    passed = sum(bool(r["passed"]) for r in records)
    return {"tasks": n, "full_app_passes": passed,
            "full_app_execution_rate": passed / n,
            "all_three_syntax_valid": sum(bool(r["syntax_valid"]) for r in records),
            "module_passes": {role: sum(bool(r["modules"][role]["passed"]) for r in records)
                              for role in MODULES},
            "failure_bins": dict(Counter(r["failure_bin"] for r in records)),
            "passed_ids": [r["task_id"] for r in records if r["passed"]]}


def run(args):
    require_sandbox()
    if args.batch_size != 4 or args.workers != 3:
        raise ValueError("Session017 frozen protocol requires batch_size=4, workers=3")
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite existing Session017 outputs")
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    tasks = contracts()
    assert len(tasks) == 10
    public = {t["task_id"]: t["public_cases"] for t in tasks}
    task_map = {t["task_id"]: t for t in tasks}
    model, tokenizer = _torch_model()
    if sum(p.numel() for p in model.parameters()) != MODEL_PARAMETER_COUNT:
        raise RuntimeError("Model parameter scale changed")

    # Track A: 30 deterministic base-model completions, exactly one per file.
    base_prompts = _prompts(tasks, MODULES)
    greedy, base_tokens = generate(model, tokenizer, base_prompts,
                                   seed=20261117, stochastic=False)
    baseline = {t["task_id"]: _assembled(t, greedy) for t in tasks}
    baseline_records = check_apps(tasks, baseline, public)
    save_json(out / "greedy-public-checks.json", baseline_records)
    print(f"Greedy baseline {metrics(baseline_records)['full_app_passes']}/10 public", flush=True)

    # Track B: one sampled alternative ONLY for public-failed modules.
    selected = choose_roles(tasks, baseline_records)
    sample_prompts = {key: base_prompts[key] for key in selected}
    sampled, sample_tokens = generate(model, tokenizer, sample_prompts,
                                      seed=20261118, stochastic=True)
    guided = {key: dict(value) for key, value in baseline.items()}
    status = {r["task_id"]: r for r in baseline_records}
    accepted = []
    for task_id, role in selected:
        task = task_map[task_id]
        proposal = dict(guided[task_id])
        proposal[role] = base_prompts[(task_id, role)] + sampled[(task_id, role)]
        tested = _one_docker(task, proposal, public[task_id])
        if score(tested) > score(status[task_id]):
            guided[task_id] = proposal
            status[task_id] = tested
            accepted.append({"task_id": task_id, "role": role, "stage": "sample"})
    save_json(out / "sample-public-checks.json", list(status.values()))
    print(f"Accepted {len(accepted)} sampled module replacements", flush=True)

    # One bounded, error-conditioned repair on remaining failures.
    unresolved = choose_roles(tasks, list(status.values()))
    repaired_prompts = {}
    for task_id, role in unresolved:
        task = task_map[task_id]
        diagnostic = status[task_id]["modules"][role]
        repaired_prompts[(task_id, role)] = make_repair_prompt(
            task, role, guided[task_id][role][len(base_prompts[(task_id, role)]):], diagnostic)
    repairs, repair_tokens = generate(model, tokenizer, repaired_prompts,
                                      seed=20261119, stochastic=True)
    for task_id, role in unresolved:
        task = task_map[task_id]
        proposal = dict(guided[task_id])
        proposal[role] = base_prompts[(task_id, role)] + repairs[(task_id, role)]
        tested = _one_docker(task, proposal, public[task_id])
        if score(tested) > score(status[task_id]):
            guided[task_id] = proposal
            status[task_id] = tested
            accepted.append({"task_id": task_id, "role": role, "stage": "repair"})
    print(f"Accepted {len(accepted)} module improvements overall", flush=True)
    del model
    gc.collect()
    save_json(out / "predictions.json", {"baseline": baseline, "guided": guided,
                                        "accepted": accepted})

    # This is the FIRST point in the process where holdout data are loaded.
    holdout = holdout_cases()
    base_final = check_apps(tasks, baseline, holdout)
    guided_final = check_apps(tasks, guided, holdout)
    public_final = [status[t["task_id"]] for t in tasks]
    for task, record in zip(tasks, guided_final, strict=True):
        export_project(out / "projects", task, guided[task["task_id"]],
                       holdout_passed=bool(record["passed"]))
    report = {
        "status": "completed", "session": "017", "model": MODEL_ID,
        "parameter_count": MODEL_PARAMETER_COUNT, "training_steps": 0,
        "dataset": {"type": "authored_fullstack_vertical_slices_not_independent_benchmark",
                    "count": len(tasks), "manifest_sha256": contract_sha256(tasks),
                    "task_ids": [t["task_id"] for t in tasks],
                    "modules_per_app": list(MODULES), "public_cases_per_app": 2,
                    "holdout_cases_per_app": 2},
        "baseline": {"holdout": metrics(base_final), "public": metrics(baseline_records),
                     "task_results": base_final},
        "guided": {"holdout": metrics(guided_final), "public": metrics(public_final),
                   "task_results": guided_final},
        "compute": {"baseline_output_tokens": base_tokens,
                    "extra_sample_output_tokens": sample_tokens,
                    "extra_repair_output_tokens": repair_tokens,
                    "total_output_tokens": base_tokens + sample_tokens + repair_tokens,
                    "wall_seconds": round(time.monotonic() - start, 2),
                    "sampled_modules": len(selected), "repaired_modules": len(unresolved)},
        "selection": {"accepted_module_edits": accepted,
                      "holdout_used_during_search": False,
                      "public_cases_are_test_spec_examples": True},
        "caveats": "Ten custom vertical-slice contracts, NOT full production applications or an independent third-party benchmark. Two held-out inputs per task; the logic contracts are publicly documented. Additional sampling and test execution increase compute. Generated code is untrusted and was executed only in restricted Docker.",
        "predictions": "experiments/session017_fullstack_predictions.json",
    }
    save_json(out / "report.json", report)
    print(json.dumps({"baseline": report["baseline"]["holdout"],
                      "guided": report["guided"]["holdout"],
                      "tokens": report["compute"]["total_output_tokens"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="outputs/session017")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=3)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
