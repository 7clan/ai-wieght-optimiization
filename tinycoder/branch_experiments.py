"""Four isolated, high-risk direct-weight interventions on Qwen2.5-Coder-0.5B.

Every variant loads a fresh base checkpoint, uses the same 20 reference pairs,
and evaluates on HumanEval/94..143 (not used in prior sessions).  No gradients,
optimizers, or training are used.  The code is intentionally experimental:
especially cross-layer transplantation and SVD erasure lack guarantees.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import platform
from pathlib import Path

VARIANTS = ("transplant", "svd_zeroing", "norm_break", "memit_single")
HOLDOUT_START = 94
HOLDOUT_COUNT = 50
TESTED_NORMS = (0.03, 0.05, 0.10)


def syntax_valid(program: str) -> bool:
    try:
        ast.parse(program)
        return True
    except (SyntaxError, ValueError):
        return False


def syntax_counts(problems, completions) -> dict:
    if len(problems) != len(completions):
        raise ValueError("Mismatched tasks and completions")
    valid = [p["task_id"] for p, code in zip(problems, completions, strict=True)
             if syntax_valid(p["prompt"] + code)]
    return {"valid": len(valid), "invalid": len(problems) - len(valid), "valid_ids": valid}


def select_pristine_holdout(problems, prior_progress: dict):
    """Reserve 94..143, excluding all 0..93 prompts from earlier sessions."""
    from .rome_batch import select_disjoint_tasks

    failures, holdout = select_disjoint_tasks(problems, prior_progress,
                                              start=HOLDOUT_START, count=HOLDOUT_COUNT)
    expected = [f"HumanEval/{i}" for i in range(HOLDOUT_START, HOLDOUT_START + HOLDOUT_COUNT)]
    if [p["task_id"] for p in holdout] != expected:
        raise ValueError("Task order changed; refusing the supposedly untouched holdout")
    if any(int(p["task_id"].split("/")[-1]) <= 93 for p in holdout):
        raise ValueError("Holdout overlaps an earlier editing/evaluation session")
    return failures, holdout


def syntax_failure_examples(failures, baseline_predictions):
    """Classify syntax failures with the *full prompt + raw completion*."""
    prior = {item["task_id"]: item for item in baseline_predictions["edited_cases"]}
    marked = []
    for item in failures:
        record = prior.get(item["task_id"])
        if not record or record.get("before_passed"):
            raise ValueError(f"Missing, non-failing historical baseline: {item['task_id']}")
        if not syntax_valid(item["prompt"] + record["before_completion"]):
            marked.append(item)
    return marked


def select_syntax_singular_modes(singular_values, right_vectors, key_differences,
                                 *, candidates: int = 16, erase: int = 2):
    """Select two top-spectrum directions with the strongest syntax-key gaps.

    A large gap is an association/proxy, NOT proof of a causal syntax circuit.
    """
    import torch

    if key_differences.ndim != 2 or key_differences.shape[1] != right_vectors.shape[1]:
        raise ValueError("Invalid SVD activation dimensions")
    if key_differences.shape[0] < 2:
        raise ValueError("At least two verified syntax-invalid completions are needed")
    top = min(candidates, singular_values.numel())
    if top < erase:
        raise ValueError("Not enough singular directions")
    projections = key_differences @ right_vectors[:top].T
    scores = singular_values[:top] * projections.abs().mean(dim=0)
    indices = torch.topk(scores, k=erase).indices.sort().values
    return indices, {
        "candidate_count": top,
        "syntax_failed_examples": key_differences.shape[0],
        "selection": indices.detach().cpu().tolist(),
        "top_singular_values": [float(v) for v in singular_values[:top].detach().cpu()],
        "association_scores": [float(v) for v in scores.detach().cpu()],
        "warning": "Syntax-invalid versus canonical activation separation is correlational, not causal",
    }


def exact_svd_erasure(weight, key_differences, *, candidates: int = 16):
    """Full SVD then exact rank-two subtraction of selected singular components."""
    import torch

    w = weight.detach().float()
    if w.ndim != 2 or not torch.isfinite(w).all():
        raise ValueError("Invalid projection matrix")
    u, singular, vh = torch.linalg.svd(w, full_matrices=False)
    indices, description = select_syntax_singular_modes(singular, vh, key_differences,
                                                         candidates=candidates)
    left = -(u[:, indices] * singular[indices]).contiguous()
    right = vh[indices, :].contiguous()
    delta = left @ right
    total = float(torch.linalg.vector_norm(w).item())
    if not torch.isfinite(delta).all() or total <= 0:
        raise RuntimeError("Non-finite SVD erasure")
    erased_projection = u[:, indices].T @ (w + delta) @ vh[indices, :].T
    description.update({
        "selected_singular_values": [float(v) for v in singular[indices].detach().cpu()],
        "relative_frobenius_change": float(torch.linalg.vector_norm(delta).item()) / total,
        "post_erasure_component_max_abs": float(erased_projection.abs().max().item()),
        "method": "full torch.linalg.svd, subtract the two selected rank-one singular components",
    })
    return left, right, description


def normalized_stress_factors(weight, left, right, requested: float):
    """Scale an existing multi-key direction to exactly the requested norm."""
    import torch

    if requested not in TESTED_NORMS:
        raise ValueError("Only the three pre-registered thresholds are permitted")
    original = float(torch.linalg.vector_norm(weight.detach().float()).item())
    delta = left.detach().float() @ right.detach().float()
    length = float(torch.linalg.vector_norm(delta).item())
    if original <= 0 or length <= 0 or not math.isfinite(length):
        raise ValueError("Cannot normalize a zero/non-finite weight edit")
    left = left * (requested * original / length)
    return left.contiguous(), right.contiguous()


def save_case_results(problems, before_completions, before_tests,
                      after_completions, after_tests, name: str):
    from .rome_batch import evaluate_records, pass_at_one_summary

    records = evaluate_records(problems, before_completions, after_completions,
                               before_tests, after_tests)
    scores = pass_at_one_summary(records)
    scores["syntax_before"] = syntax_counts(problems, before_completions)
    scores["syntax_after"] = syntax_counts(problems, after_completions)
    scores["variant_name"] = name
    return scores, records


def validate_branch_config(path: Path, variant: str):
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("variant") != variant or config.get("holdout_start") != HOLDOUT_START:
        raise ValueError("Experiment branch metadata differs from selected variant/holdout")
    return config


def run(args):
    import torch
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .rome_batch import (apply_batch_factors, batch_factors, capture_activations,
                             generate_batches, parallel_execution)
    from .sandbox_eval import require_sandbox
    from .weight_space import capture_io, matrix_statistics, target_linear

    if args.variant not in VARIANTS:
        raise ValueError("Unsupported experiment")
    validate_branch_config(Path(args.branch_config), args.variant)
    require_sandbox()
    torch.set_num_threads(4)
    torch.manual_seed(0)
    device = torch.device("cpu")
    destination = Path(args.output_dir)
    if any((destination / path).exists() for path in ("report.json", "factors.safetensors", "predictions.json")):
        raise FileExistsError("Outputs already exist; use a fresh experiment directory")

    prior = json.loads(Path(args.source_progress).read_text(encoding="utf-8"))
    if prior.get("base_model") != BASE_MODEL or prior.get("source") != DATA_URL:
        raise ValueError("Original failure set model or dataset is inconsistent")
    problems = fetch_problems()
    failures, holdout = select_pristine_holdout(problems, prior)
    print(f"{args.variant}: loading base {BASE_MODEL}, CPU with 4 threads", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.float32).eval().to(device)
    print("Computing baseline for 50 never-used HumanEval tasks...", flush=True)
    base_completions = generate_batches(model, tokenizer, holdout, device=device,
                                        batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    base_tests = parallel_execution(holdout, base_completions,
                                    workers=args.workers, timeout=args.exec_timeout)
    save_json(destination / "progress.json", {
        "status": "baseline_complete", "variant": args.variant,
        "baseline_passes": sum(bool(x["passed"]) for x in base_tests),
        "holdout_ids": [x["task_id"] for x in holdout],
    })

    factors = {}
    modifications = {}
    results = {}
    predictions = {}

    if args.variant in ("transplant", "memit_single", "norm_break"):
        print("Capturing 20 failing-key and teacher-forced reference pairs...", flush=True)
        keys, values = [], []
        value_layer = 18 if args.variant == "transplant" else 8
        for idx, item in enumerate(failures, 1):
            failed, _ = capture_activations(model, tokenizer, item["prompt"], device)
            successful, _ = capture_activations(model, tokenizer,
                                                item["prompt"] + item["canonical_solution"], device)
            keys.append(failed[8]["key"])
            values.append(successful[value_layer]["value"])
            print(f"  key/value pair {idx}/{len(failures)}", flush=True)
        k = torch.stack(keys, dim=1)
        y = torch.stack(values, dim=1)
        linear = target_linear(model, 8, "mlp.down_proj")
        original = linear.weight.detach().clone()
        left, right, details = batch_factors(linear.weight, k, y,
                                              max_relative_change=0.015)

        if args.variant == "norm_break":
            baseline_valid = syntax_counts(holdout, base_completions)["valid"]
            stress = {}
            for threshold in TESTED_NORMS:
                with torch.no_grad():
                    linear.weight.copy_(original)
                scaled_left, scaled_right = normalized_stress_factors(original, left, right, threshold)
                observed = apply_batch_factors(model, 8, scaled_left, scaled_right,
                                                threshold + 1e-6)
                label = f"{threshold:.0%}"
                # Store independent tensor memory for each stress threshold.
                # safetensors refuses shared storage across checkpoint keys.
                factors[f"{label}.layer8.left"] = scaled_left.detach().cpu().contiguous().clone()
                factors[f"{label}.layer8.right"] = scaled_right.detach().cpu().contiguous().clone()
                completions = generate_batches(model, tokenizer, holdout, device=device,
                                               batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
                tests = parallel_execution(holdout, completions,
                                           workers=args.workers, timeout=args.exec_timeout)
                score, records = save_case_results(holdout, base_completions, base_tests,
                                                   completions, tests, label)
                score["observed_relative_delta_norm"] = observed
                score["syntax_validity_decreased"] = score["syntax_after"]["valid"] < baseline_valid
                stress[label] = score
                predictions[label] = records
                print(f"  {label} stress: {score['before_passes']} -> {score['after_passes']} passes", flush=True)
                save_json(destination / "progress.json", {"status": f"stress_{label}_complete", "variant": args.variant,
                                                          "finished_thresholds": list(stress)})
            with torch.no_grad():
                linear.weight.copy_(original)
            impaired = [label for label, row in stress.items()
                        if row["after_passes"] < row["before_passes"] or row["syntax_validity_decreased"]]
            modifications = {"layer": 8, "matrix": "mlp.down_proj", "base_rank": k.shape[1],
                             "direction_derivation": details,
                             "tested_thresholds": list(stress),
                             "first_observed_breakdown": impaired[0] if impaired else None,
                             "breakdown_definition": "first tested threshold with fewer passes or fewer syntax-valid completions",
                             "precision_warning": "Three specified thresholds cannot determine an exact continuous breakdown limit"}
            results = stress
        else:
            observed = apply_batch_factors(model, 8, left, right, 0.015)
            factors["layer8.left"] = left.detach().cpu().contiguous()
            factors["layer8.right"] = right.detach().cpu().contiguous()
            modifications = {"layer": 8, "matrix": "mlp.down_proj", "source_value_layer": value_layer,
                             "observed_relative_delta_norm": observed,
                             "before": matrix_statistics(original),
                             "after": matrix_statistics(linear.weight), **details}
            if args.variant == "transplant":
                modifications["warning"] = ("Layer 18 teacher-forced MLP output is projected onto layer 8 "
                                            "only because the hidden sizes agree; this is not a causal transplant")

    elif args.variant == "svd_zeroing":
        prior_predictions = json.loads(Path(args.prior_predictions).read_text(encoding="utf-8"))
        syntax_cases = syntax_failure_examples(failures, prior_predictions)
        if len(syntax_cases) < 2:
            raise RuntimeError("Insufficient verified syntax-invalid historical failures for SVD association")
        print(f"Associating SVD components with {len(syntax_cases)} syntax-invalid baselines...", flush=True)
        # Capture both matrices' syntax-reference gaps *before* changing either.
        original_gaps = {}
        for matrix_name in ("self_attn.o_proj", "mlp.down_proj"):
            gaps = []
            for item in syntax_cases:
                failure_key, _ = capture_io(model, tokenizer, item["prompt"], 8, matrix_name)
                success_key, _ = capture_io(model, tokenizer,
                                            item["prompt"] + item["canonical_solution"], 8, matrix_name)
                gaps.append(failure_key - success_key)
            original_gaps[matrix_name] = torch.stack(gaps)
        for matrix_name in ("self_attn.o_proj", "mlp.down_proj"):
            module = target_linear(model, 8, matrix_name)
            original = module.weight.detach().clone()
            left, right, details = exact_svd_erasure(module.weight, original_gaps[matrix_name], candidates=16)
            with torch.no_grad():
                module.weight.add_(left @ right)
            if not torch.isfinite(module.weight).all():
                with torch.no_grad():
                    module.weight.copy_(original)
                raise RuntimeError("SVD zeroing produced non-finite tensor")
            tag = matrix_name.replace(".", "_")
            factors[f"{tag}.left"] = left.detach().cpu().contiguous()
            factors[f"{tag}.right"] = right.detach().cpu().contiguous()
            modifications[matrix_name] = {"before": matrix_statistics(original),
                                          "after": matrix_statistics(module.weight), **details}
            print(f"  {matrix_name}: erased modes {details['selection']}", flush=True)
        modifications["syntax_invalid_training_ids"] = [p["task_id"] for p in syntax_cases]

    if args.variant != "norm_break":
        print("Post-edit coding on 50 pristine evaluation tasks...", flush=True)
        completions = generate_batches(model, tokenizer, holdout, device=device,
                                       batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
        tests = parallel_execution(holdout, completions, workers=args.workers, timeout=args.exec_timeout)
        score, records = save_case_results(holdout, base_completions, base_tests,
                                           completions, tests, args.variant)
        results = {"default": score}
        predictions = {"default": records}

    destination.mkdir(parents=True, exist_ok=True)
    save_file(factors, str(destination / "factors.safetensors"))
    report = {
        "status": "completed", "variant": args.variant,
        "base_model": BASE_MODEL, "dataset": DATA_URL,
        "hardware": {"device": "cpu", "pytorch_threads": torch.get_num_threads(),
                     "torch_version": torch.__version__, "python_version": platform.python_version()},
        "failure_reference_ids": [p["task_id"] for p in failures],
        "holdout_ids": [p["task_id"] for p in holdout],
        "intervention": modifications,
        "variants": results,
        "no_training": True,
        "methodological_limit": ("Same 50 holdout tasks compare four pre-specified interventions. "
                                 "Future optimization based on these scores needs a NEW test set. "
                                 "SVD association and cross-layer transfer are exploratory, not established mechanisms."),
    }
    save_json(destination / "report.json", report)
    save_json(destination / "predictions.json", {"variant": args.variant, "variants": predictions})
    save_json(destination / "progress.json", {"status": "completed", "variant": args.variant,
                                              "scores": {v: {"before": x["before_passes"],
                                                              "after": x["after_passes"]} for v, x in results.items()}})
    print(f"COMPLETED {args.variant}: " + json.dumps({v: (x["before_passes"], x["after_passes"])
                                                   for v, x in results.items()}), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run an isolated direct-weight research branch on CPU")
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--branch-config", default="experiments/branch_spec.json")
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--prior-predictions", default="experiments/2026-11-04-rome20/predictions.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--exec-timeout", type=int, default=4)
    args = parser.parse_args()
    if not (1 <= args.batch_size <= 8 and 1 <= args.workers <= 8
            and 32 <= args.max_new_tokens <= 512 and 1 <= args.exec_timeout <= 30):
        parser.error("Invalid model batch, sandbox worker, token, or timeout setting")
    run(args)


if __name__ == "__main__":
    main()
