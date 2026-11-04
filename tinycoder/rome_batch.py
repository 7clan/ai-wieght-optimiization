"""GPU-only, gradient-free two-layer batch editing experiment.

This is a MEMIT-*style* multi-key ridge update, not the full MEMIT algorithm.
Neither a reference solution's last-token MLP activation nor a causal
first-token score establishes that the edit encodes a correct program.
Execution results on a disjoint holdout are the deciding measurement.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, patched_first_token_logprob, save_json, text_tensor

TARGET_LAYERS = (8, 12)
DEFAULT_FAILURE_SET = "experiments/2026-11-04-rome20/progress.json"
RESULTS_START = "<!-- ROME-BATCH-RESULTS-START -->"
RESULTS_END = "<!-- ROME-BATCH-RESULTS-END -->"


def select_disjoint_tasks(problems, prior_progress: dict, *, start: int, count: int):
    """Do not reuse anything from the preceding 20+20 experiment."""
    by_id = {item["task_id"]: item for item in problems}
    failure_ids = prior_progress["selected_failing_ids"]
    prior_holdout = prior_progress["holdout_ids"]
    if len(failure_ids) != 20 or len(set(failure_ids)) != 20:
        raise ValueError("Expected exactly 20 unique, previously verified failures")
    if not isinstance(start, int) or not isinstance(count, int) or start < 0 or count != 50:
        raise ValueError("This protocol requires exactly 50 contiguous holdout tasks")
    holdout = problems[start:start + count]
    if len(holdout) != count:
        raise ValueError("Insufficient HumanEval tasks for the requested holdout")
    overlap = set(failure_ids) | set(prior_holdout)
    if any(item["task_id"] in overlap for item in holdout):
        raise ValueError("Holdout intersects previously used failure/edit/holdout tasks")
    if any(task_id not in by_id for task_id in failure_ids):
        raise ValueError("Stored failure IDs do not match the pinned HumanEval dataset")
    if prior_progress.get("base_model") != BASE_MODEL or prior_progress.get("source") != DATA_URL:
        raise ValueError("Previous failure-set checkpoint is for a different model/dataset")
    return [by_id[task_id] for task_id in failure_ids], holdout


def capture_cuda_activations(model, tokenizer, text: str):
    """Keep 24 down_proj keys and outputs resident on CUDA, in float32."""
    import torch

    observed = {}
    handles = []
    for index, block in enumerate(model.model.layers):
        def record(_module, arguments, output, layer=index):
            observed[layer] = {
                "key": arguments[0][0, -1].detach().float().clone(),
                "value": output[0, -1].detach().float().clone(),
            }

        handles.append(block.mlp.down_proj.register_forward_hook(record))
    try:
        input_ids = text_tensor(tokenizer, text, torch.device("cuda"))
        with torch.inference_mode():
            logits = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids)).logits[0, -1]
        logits = logits.detach().float().clone()
    finally:
        for handle in handles:
            handle.remove()
    if len(observed) != len(model.model.layers):
        raise RuntimeError("CUDA capture failed to visit every MLP down projection")
    if not all(entry["key"].is_cuda and entry["value"].is_cuda for entry in observed.values()):
        raise RuntimeError("Activation extraction unexpectedly moved data off CUDA")
    return observed, logits


def covariance_inverse_keys(calibration_keys, queries, ridge_fraction: float = 0.01):
    """C^-1 Q using Woodbury; C = lambda I + calibration @ calibration.T / m.

    Shape: calibration (input_dim, m), queries (input_dim, n).
    The dense input_dim x input_dim covariance is never constructed.
    """
    import torch

    if calibration_keys.ndim != 2 or queries.ndim != 2 or calibration_keys.shape[0] != queries.shape[0]:
        raise ValueError("Covariance keys must have compatible 2D input dimensions")
    if calibration_keys.shape[1] == 0 or queries.shape[1] == 0:
        raise ValueError("Nonempty key batches are required")
    if not 0 < ridge_fraction <= 1:
        raise ValueError("Invalid ridge regularization")
    k = calibration_keys.detach().float()
    q = queries.detach().float()
    if k.device != q.device or not torch.isfinite(k).all() or not torch.isfinite(q).all():
        raise ValueError("Keys must share a device and contain finite values")
    ridge = max(float(k.square().mean().item()) * ridge_fraction, 1e-5)
    u = k / math.sqrt(k.shape[1])
    small = ridge * torch.eye(u.shape[1], device=k.device, dtype=k.dtype) + u.T @ u
    inverse = (q - u @ torch.linalg.solve(small, u.T @ q)) / ridge
    if not torch.isfinite(inverse).all():
        raise RuntimeError("Non-finite Woodbury inverse; aborting weight update")
    return inverse, ridge


def batch_factors(weight, keys, targets, *, max_relative_change: float,
                  ridge_fraction: float = 0.01, residual_fraction: float = 1.0):
    """Multi-key closed-form ridge edit ΔW = R (I + K^T C^-1 K)^-1 (C^-1 K)^T.

    L @ R is capped by the *exact*, not rank-one-approximated, Frobenius norm.
    """
    import torch

    if not 0 < max_relative_change <= 0.015 or not 0 < residual_fraction <= 1:
        raise ValueError("Bound must be <= 1.5% and residual_fraction in (0, 1]")
    w = weight.detach().float()
    k = keys.detach().float()
    y = targets.detach().float()
    if w.ndim != 2 or k.ndim != 2 or y.shape != (w.shape[0], k.shape[1]) or k.shape[0] != w.shape[1]:
        raise ValueError("Weight/key/value dimensions do not match")
    if not (w.device == k.device == y.device) or not all(torch.isfinite(v).all() for v in (w, k, y)):
        raise ValueError("Weights/keys/values must share a device and contain finite values")
    inverse_keys, ridge = covariance_inverse_keys(k, k, ridge_fraction)
    gram = torch.eye(k.shape[1], device=k.device) + k.T @ inverse_keys
    residual = residual_fraction * (y - w @ k)
    left = torch.linalg.solve(gram.T, residual.T).T.contiguous()
    right = inverse_keys.T.contiguous()
    delta = left @ right
    proposal = float(torch.linalg.vector_norm(delta).item())
    wnorm = float(torch.linalg.vector_norm(w).item())
    if proposal <= 0 or not math.isfinite(proposal) or wnorm <= 0:
        raise ValueError("Degenerate batch edit or base layer")
    # A small numerical margin ensures the observed edited matrix is <= 1.5%.
    scale = min(1.0, max_relative_change * wnorm * 0.999 / proposal)
    left = (left * scale).contiguous()
    delta = left @ right
    actual_fraction = float(torch.linalg.vector_norm(delta).item()) / wnorm
    if actual_fraction > max_relative_change + 1e-7 or not torch.isfinite(delta).all():
        raise RuntimeError("Batch update violates norm cap or has invalid floats")
    before_dist = float(torch.linalg.vector_norm(w @ k - y).item())
    after_dist = float(torch.linalg.vector_norm((w + delta) @ k - y).item())
    return left, right, {
        "ridge": ridge,
        "rank_upper_bound": k.shape[1],
        "proposed_delta_frob_norm": proposal,
        "factor_scale": scale,
        "relative_delta_frob_norm": actual_fraction,
        "target_distance_before": before_dist,
        "target_distance_after": after_dist,
        "residual_fraction": residual_fraction,
    }


def apply_batch_factors(model, layer: int, left, right, max_relative_change: float):
    """Change raw weights without gradients; verify the *observed* change."""
    import torch

    from .weight_space import target_linear

    module = target_linear(model, layer, "mlp.down_proj")
    w = module.weight
    if left.shape != (w.shape[0], right.shape[0]) or right.shape[1] != w.shape[1]:
        raise ValueError("Invalid saved factor dimensions")
    if not (left.device == right.device == w.device) or not torch.isfinite(left).all() or not torch.isfinite(right).all():
        raise ValueError("Invalid batch factor values/devices")
    delta = (left @ right).to(dtype=w.dtype)
    with torch.no_grad():
        old = w.detach().clone()
        w.add_(delta)
        observed = float(torch.linalg.vector_norm((w - old).float()).item())
        relative = observed / float(torch.linalg.vector_norm(old.float()).item())
        if not torch.isfinite(w).all() or relative > max_relative_change + 1e-6:
            w.copy_(old)
            raise RuntimeError("Applied batch edit exceeded cap; original layer restored")
    return relative


def gpu_generate_batches(model, tokenizer, problems, *, batch_size: int, max_new_tokens: int):
    """Left-padded greedy GPU decoding, preserving the supplied problem order."""
    import torch

    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    answers = []
    for start in range(0, len(problems), batch_size):
        part = problems[start:start + batch_size]
        encoded = tokenizer([p["prompt"] for p in part], return_tensors="pt", padding=True,
                            add_special_tokens=False).to("cuda")
        with torch.inference_mode():
            generated = model.generate(
                **encoded, do_sample=False, max_new_tokens=max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
            )
        prefix_length = encoded["input_ids"].shape[1]
        answers.extend(tokenizer.batch_decode(generated[:, prefix_length:], skip_special_tokens=True))
        print(f"  GPU generation {min(start + batch_size, len(problems))}/{len(problems)}", flush=True)
    return answers


def parallel_execution(problems, completions, *, workers: int, timeout: int):
    """Run only sandboxed subprocesses concurrently; never execute on host."""
    from .sandbox_eval import evaluate_completion

    if len(problems) != len(completions):
        raise ValueError("Mismatched completions and tests")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: evaluate_completion(p[0], p[1], timeout=timeout),
                                zip(problems, completions)))
    return results


def evaluate_records(problems, before, after, before_results, after_results):
    records = []
    for problem, old, new, a, b in zip(problems, before, after, before_results, after_results, strict=True):
        records.append({
            "task_id": problem["task_id"],
            "before_passed": bool(a["passed"]), "after_passed": bool(b["passed"]),
            "before_error": a["error"], "after_error": b["error"],
            "before_completion": old, "after_completion": new,
        })
    return records


def pass_at_one_summary(records):
    n = len(records)
    if n != 50 or len({r["task_id"] for r in records}) != 50:
        raise ValueError("Exactly 50 unique holdout records are required")
    passed_before = [r["task_id"] for r in records if r["before_passed"]]
    passed_after = [r["task_id"] for r in records if r["after_passed"]]
    return {
        "n": n,
        "before_passes": len(passed_before), "after_passes": len(passed_after),
        "pass_at_1_before": len(passed_before) / n,
        "pass_at_1_after": len(passed_after) / n,
        "percentage_point_delta": 100 * (len(passed_after) - len(passed_before)) / n,
        "passed_ids_before": passed_before, "passed_ids_after": passed_after,
        "failed_ids_before": [r["task_id"] for r in records if not r["before_passed"]],
        "failed_ids_after": [r["task_id"] for r in records if not r["after_passed"]],
        "newly_passed_ids": [r["task_id"] for r in records if not r["before_passed"] and r["after_passed"]],
        "regressed_ids": [r["task_id"] for r in records if r["before_passed"] and not r["after_passed"]],
        "changed_completions": sum(r["before_completion"] != r["after_completion"] for r in records),
    }


def update_readme(readme: Path, report: dict):
    """Update only the dedicated bounded result region when a real run succeeds."""
    body = readme.read_text(encoding="utf-8")
    if body.count(RESULTS_START) != 1 or body.count(RESULTS_END) != 1:
        raise RuntimeError("README is missing its unique batch-results markers")
    score = report["independent_holdout_50"]
    new_section = (
        f"{RESULTS_START}\n"
        f"**GPU batch experiment:** {report['status']} on {report['hardware']['gpu_name']}. "
        f"A direct two-layer (8, 12) MEMIT-style update, at most 1.5% of the "
        f"original Frobenius norm per layer, changed independent HumanEval "
        f"pass@1 **{score['before_passes']}/50 → {score['after_passes']}/50** "
        f"(**{score['percentage_point_delta']:+.1f} percentage points**). "
        f"New passes: {score['newly_passed_ids']}; regressions: {score['regressed_ids']}. "
        f"See [`experiments/rome_batch_report.json`](experiments/rome_batch_report.json) "
        f"and [`experiments/rome_batch_factors.safetensors`](experiments/rome_batch_factors.safetensors). "
        f"This limited holdout alone does not prove general improvement.\n"
        f"{RESULTS_END}"
    )
    first = body.index(RESULTS_START)
    last = body.index(RESULTS_END) + len(RESULTS_END)
    readme.write_text(body[:first] + new_section + body[last:], encoding="utf-8")


def run(args):
    import torch
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .sandbox_eval import require_sandbox
    from .weight_space import matrix_statistics

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for this protocol; refusing silent CPU fallback")
    require_sandbox()
    torch.manual_seed(0)
    torch.backends.cuda.matmul.allow_tf32 = True  # Fast-mode GPU algebra; logged below.
    device = torch.device("cuda:0")
    destination = Path(args.output_dir)
    factor_path = destination / "rome_batch_factors.safetensors"
    report_path = destination / "rome_batch_report.json"
    predictions_path = destination / "rome_batch_predictions.json"
    if any(p.exists() and p.stat().st_size > 0 for p in (factor_path, predictions_path)):
        raise FileExistsError("Batch factors/results already exist; choose a new output directory")
    prior = json.loads(Path(args.source_progress).read_text(encoding="utf-8"))
    problems = fetch_problems()
    failures, holdout = select_disjoint_tasks(problems, prior, start=args.holdout_start,
                                              count=args.holdout_count)
    print(f"Loading base {BASE_MODEL} directly onto CUDA (no training)", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.float32).eval().to(device)
    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

    print("Greedy baseline for 50 previously untouched HumanEval tasks...", flush=True)
    baseline = gpu_generate_batches(model, tokenizer, holdout,
                                     batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    baseline_tests = parallel_execution(holdout, baseline, workers=args.workers, timeout=args.exec_timeout)
    save_json(destination / "rome_batch_progress.json", {
        "phase": "baseline_complete", "baseline_passes": sum(r["passed"] for r in baseline_tests),
        "holdout_ids": [p["task_id"] for p in holdout],
    })

    print("CUDA key/value capture from original failing prompts and canonical solutions...", flush=True)
    pairs = []
    for index, problem in enumerate(failures, 1):
        fail, logits = capture_cuda_activations(model, tokenizer, problem["prompt"])
        success, _ = capture_cuda_activations(model, tokenizer, problem["prompt"] + problem["canonical_solution"])
        reference_token = tokenizer(problem["canonical_solution"], add_special_tokens=False)["input_ids"][0]
        base_logprob = float(torch.log_softmax(logits, dim=-1)[reference_token].item())
        pairs.append({"problem": problem, "failure": fail, "successful": success,
                      "reference_token": reference_token, "base_logprob": base_logprob})
        print(f"  CUDA extraction {index}/{len(failures)}", flush=True)

    print("CUDA causal tracing: patching each MLP projection in all 24 layers...", flush=True)
    causal_scores = []
    for layer in range(len(model.model.layers)):
        changes = [patched_first_token_logprob(model, tokenizer, item["problem"]["prompt"], layer,
                                               item["successful"][layer]["value"], item["reference_token"])
                   - item["base_logprob"] for item in pairs]
        causal_scores.append({"layer": layer, "mean_logprob_delta": statistics.mean(changes),
                              "positive_cases": sum(x > 0 for x in changes), "cases": len(changes)})
        print(f"  layer {layer:02d}: mean Δlogprob {statistics.mean(changes):+.6f}", flush=True)
    causal_ranked = sorted(causal_scores, key=lambda x: x["mean_logprob_delta"], reverse=True)
    print(f"Target layer ranks: { {layer: [v['layer'] for v in causal_ranked].index(layer)+1 for layer in TARGET_LAYERS} }", flush=True)

    edits, factors = {}, {}
    for layer_index, layer in enumerate(TARGET_LAYERS):
        module = model.model.layers[layer].mlp.down_proj
        keys = torch.stack([p["failure"][layer]["key"] for p in pairs], dim=1)
        targets = torch.stack([p["successful"][layer]["value"] for p in pairs], dim=1)
        # Account for propagation of the earlier layer edit in the later key distribution.
        if layer_index:
            fresh = [capture_cuda_activations(model, tokenizer, p["problem"]["prompt"])[0][layer]["key"]
                     for p in pairs]
            keys = torch.stack(fresh, dim=1)
        before = matrix_statistics(module.weight)
        left, right, details = batch_factors(module.weight, keys, targets,
                                              max_relative_change=args.max_relative_change,
                                              residual_fraction=1 / (len(TARGET_LAYERS) - layer_index))
        observed = apply_batch_factors(model, layer, left, right, args.max_relative_change)
        after = matrix_statistics(module.weight)
        factors[f"layer{layer}.left"] = left.detach().cpu().contiguous()
        factors[f"layer{layer}.right"] = right.detach().cpu().contiguous()
        edits[str(layer)] = {"matrix": "mlp.down_proj", "before": before, "after": after,
                             "observed_relative_delta_norm": observed, **details}
        print(f"  edited layer {layer}, observed ΔW/W={observed:.6%}", flush=True)
    destination.mkdir(parents=True, exist_ok=True)
    save_file(factors, str(factor_path))

    print("Post-edit generation and parallel sandbox execution on independent 50...", flush=True)
    changed = gpu_generate_batches(model, tokenizer, holdout,
                                    batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    changed_tests = parallel_execution(holdout, changed, workers=args.workers, timeout=args.exec_timeout)
    records = evaluate_records(holdout, baseline, changed, baseline_tests, changed_tests)
    summary = pass_at_one_summary(records)
    report = {
        "status": "completed", "completed_utc": datetime.now(timezone.utc).isoformat(),
        "base_model": BASE_MODEL, "source": DATA_URL,
        "hardware": {"device": "cuda:0", "gpu_name": torch.cuda.get_device_name(0),
                     "cuda_version": torch.version.cuda, "torch_version": torch.__version__,
                     "python": platform.python_version(), "tf32_allowed": True},
        "failure_ids": [p["task_id"] for p in failures],
        "independent_holdout_ids": [p["task_id"] for p in holdout],
        "causal_scores_all_24_layers": causal_scores,
        "causal_target_ranks": {str(layer): [c["layer"] for c in causal_ranked].index(layer) + 1
                                for layer in TARGET_LAYERS},
        "target_layers": list(TARGET_LAYERS), "matrix": "mlp.down_proj",
        "max_relative_change": args.max_relative_change,
        "edits": edits, "independent_holdout_50": summary,
        "execution": {"generation": "greedy left-padded CUDA batches", "max_new_tokens": args.max_new_tokens,
                      "batch_size": args.batch_size, "docker_parallel_workers": args.workers,
                      "sandbox": "no network, read-only filesystem, unprivileged, limited CPU/memory"},
        "methodology": "MEMIT-style multi-key Woodbury ridge updates with sequential residual splitting, "
                       "not exact MEMIT; no gradient/backprop/optimizer. Teacher-forced canonical last-token "
                       "MLP outputs are unaligned proxies, not learned target representations.",
        "caution": "50 deterministic tasks provide only a small non-random holdout and do not establish generalization",
    }
    save_json(predictions_path, {"holdout_records": records})
    save_json(report_path, report)
    update_readme(Path(args.readme), report)
    save_json(destination / "rome_batch_progress.json", {"phase": "completed", "holdout": summary})
    print("INDEPENDENT HOLDOUT 50 before/after:", summary, flush=True)
    print(f"Saved reversible factors and reports in {destination}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="CUDA-only, closed-form multi-layer MEMIT-style batch experiment")
    parser.add_argument("--source-progress", default=DEFAULT_FAILURE_SET)
    parser.add_argument("--holdout-start", type=int, default=44)
    parser.add_argument("--holdout-count", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--exec-timeout", type=int, default=4)
    parser.add_argument("--max-relative-change", type=float, default=0.015)
    parser.add_argument("--output-dir", default="experiments")
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()
    if not (1 <= args.batch_size <= 16 and 1 <= args.workers <= 8 and 32 <= args.max_new_tokens <= 512):
        parser.error("batch-size/workers/max-new-tokens out of accepted range")
    if not (1 <= args.exec_timeout <= 30 and 0 < args.max_relative_change <= 0.015):
        parser.error("Execution timeout must be 1..30 and maximum weight change <= 1.5%")
    run(args)


if __name__ == "__main__":
    main()
