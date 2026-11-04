"""Session 011: reversible CPU-only multi-key norm stress and rank-32 surgery.

Only archived failures below HumanEval/94 determine edit factors. The 70-task
comparison has been used repeatedly and is NOT an independent holdout. This is
an exploratory MEMIT-style closed-form ridge edit, not the original MEMIT.
No gradients, optimization or unsandboxed generated-code execution are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

SOURCE_COUNT = 50
START, STOP = 94, 164
STRESS_LAYERS = (6, 8, 10, 14)
RANK32_TARGETS = ((8, "mlp.down_proj"), (13, "self_attn.o_proj"),
                  (15, "self_attn.o_proj"))
STRESS_LEVELS = (0.15, 0.30, 0.50)
RANK = 32


def select_fifty(problems: list[dict], archive: dict, progress: dict) -> list[dict]:
    """46 archived actual failures on 44..93 + four verified original failures."""
    from .rome20 import BASE_MODEL, DATA_URL

    rows = archive.get("holdout_records", [])
    expected = [f"HumanEval/{n}" for n in range(44, 94)]
    if [r["task_id"] for r in rows] != expected:
        raise ValueError("Archived 50-task baseline IDs or ordering changed")
    if progress.get("base_model") != BASE_MODEL or progress.get("source") != DATA_URL:
        raise ValueError("Original verified failure set provenance changed")
    original = progress.get("selected_failing_ids", [])
    if len(original) != 20 or len(set(original)) != 20 or not all(
            int(x.split("/")[-1]) < 44 for x in original):
        raise ValueError("Original 20 selected failures invalid")
    archived_failures = [r["task_id"] for r in rows if r["before_passed"] is False]
    if len(archived_failures) != 46:
        raise ValueError("Expect exactly 46 archived baseline failures on 44..93")
    ids = original[:4] + archived_failures
    if len(ids) != SOURCE_COUNT or len(set(ids)) != SOURCE_COUNT or any(
            int(x.split("/")[-1]) >= START for x in ids):
        raise RuntimeError("Leaky or incomplete failure-conditioned edit set")
    by_id = {x["task_id"]: x for x in problems}
    if not all(x in by_id for x in ids):
        raise ValueError("Failure ID missing from pinned HumanEval")
    return [by_id[x] for x in ids]


def target_name(layer, name):
    return f"layer{layer}.{name.replace('.', '_')}"


def capture_keys(model, tokenizer, source: str, targets):
    """Capture the input of each projection at the final teacher-forced token."""
    import torch
    from .rome20 import text_tensor
    from .weight_space import target_linear

    captures, hooks = {}, []
    for layer, name in targets:
        label = target_name(layer, name)

        def capture(_module, inputs, _output, label=label):
            captures[label] = inputs[0][0, -1].detach().float().cpu().clone()

        hooks.append(target_linear(model, layer, name).register_forward_hook(capture))
    try:
        ids = text_tensor(tokenizer, source, torch.device("cpu"))
        with torch.inference_mode():
            model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False)
    finally:
        for hook in hooks:
            hook.remove()
    if set(captures) != {target_name(*item) for item in targets}:
        raise RuntimeError("Missing projection activation capture")
    if not all(torch.isfinite(x).all() for x in captures.values()):
        raise ValueError("Invalid activation values")
    return captures


def collect_pairs(model, tokenizer, source, targets):
    failure, teacher = {target_name(*t): [] for t in targets}, {target_name(*t): [] for t in targets}
    for i, problem in enumerate(source, 1):
        failed = capture_keys(model, tokenizer, problem["prompt"], targets)
        reference = capture_keys(model, tokenizer,
                                 problem["prompt"] + problem["canonical_solution"], targets)
        for key in failure:
            failure[key].append(failed[key])
            teacher[key].append(reference[key])
        print(f"  frozen source failure/reference pair {i}/{len(source)}", flush=True)
    return failure, teacher


def multi_key_ridge(weight, failed_inputs, teacher_inputs, *, rank=None):
    """Closed-form ridge solution with optional truncated thin-QR SVD.

    Delta = W (T-K) (K'K + ridge I)^-1 K'. The reference *inputs* are
    activation targets, not verified causal directions of correct logic.
    """
    import torch

    w = weight.detach().float().cpu()
    k = torch.stack(failed_inputs, 1).float().cpu()
    t = torch.stack(teacher_inputs, 1).float().cpu()
    if w.ndim != 2 or k.shape != (w.shape[1], SOURCE_COUNT) or t.shape != k.shape:
        raise ValueError("Key/teacher projection dimensions invalid")
    if not all(torch.isfinite(x).all() for x in (w, k, t)):
        raise ValueError("Non-finite key/teacher/weight")
    gram = k.T @ k
    ridge = max(float(gram.diag().mean()) * 0.0001, 0.0001)
    residual = w @ (t - k)
    left_full = torch.linalg.solve(
        gram + ridge * torch.eye(SOURCE_COUNT), residual.T).T.contiguous()
    right_full = k.T.contiguous()
    singular_values = None
    if rank is not None:
        if not (1 <= rank <= SOURCE_COUNT):
            raise ValueError("Unsupported SVD rank")
        # Full weight SVD is unnecessary: only SVD of a 50x50 core.
        qu, ru = torch.linalg.qr(left_full, mode="reduced")
        qv, rv = torch.linalg.qr(k, mode="reduced")
        u, s, vh = torch.linalg.svd(ru @ rv.T, full_matrices=False)
        if int((s > 1e-7).sum().item()) < rank:
            raise RuntimeError("Source activation difference rank below requested rank")
        root = s[:rank].clamp_min(0).sqrt()
        left = ((qu @ u[:, :rank]) * root[None, :]).contiguous()
        right = (root[:, None] * (vh[:rank, :] @ qv.T)).contiguous()
        singular_values = [float(x) for x in s[:rank]]
    else:
        left, right = left_full, right_full
    delta_norm = float(torch.linalg.vector_norm(left @ right).item())
    norm = float(torch.linalg.vector_norm(w).item())
    if norm <= 0 or delta_norm <= 0 or not math.isfinite(delta_norm):
        raise RuntimeError("Degenerate or non-finite closed-form delta")
    if not all(torch.isfinite(x).all() for x in (left, right)):
        raise RuntimeError("Non-finite factors")
    return left, right, {"ridge": ridge, "rank_upper_bound": rank or SOURCE_COUNT,
                          "raw_relative_norm": delta_norm / norm,
                          "top_singular_values": singular_values,
                          "method": "50-key ridge solution, optionally SVD truncated by thin QR"}


def scaled_factors(left, right, weight, requested):
    """Scale to the *specified stress magnitude*, even when above raw edit."""
    import torch

    raw_ratio = float((torch.linalg.vector_norm(left @ right) /
                       torch.linalg.vector_norm(weight.detach().float().cpu())).item())
    if raw_ratio <= 0 or not math.isfinite(raw_ratio):
        raise ValueError("No finite nonzero edit direction")
    scale = requested / raw_ratio
    return (left * scale).contiguous(), right, scale


def apply_factors(module, left, right):
    import torch

    before = module.weight.detach().clone()
    if (left.shape[0] != before.shape[0] or right.shape[1] != before.shape[1]
            or left.shape[1] != right.shape[0]):
        raise ValueError("Factor shape does not match matrix")
    delta = left @ right
    if not torch.isfinite(delta).all():
        raise ValueError("Invalid delta")
    with torch.no_grad():
        module.weight.add_(delta.to(module.weight.dtype).to(module.weight.device))
    relative = float((torch.linalg.vector_norm((module.weight - before).float()) /
                      torch.linalg.vector_norm(before.float())).item())
    return before, relative, bool(torch.isfinite(module.weight).all())


def restore(model, originals):
    import torch
    from .weight_space import target_linear

    with torch.no_grad():
        for (layer, name), before in originals.items():
            target_linear(model, layer, name).weight.copy_(before)


def probe(model, tokenizer, prompts, references):
    """Fixed-input next-token entropy and reference-token perplexity; no sampling."""
    import torch
    from .rome20 import text_tensor

    entropy = []
    with torch.inference_mode():
        for prompt in prompts:
            ids = text_tensor(tokenizer, prompt, torch.device("cpu"))
            logits = model(input_ids=ids, attention_mask=torch.ones_like(ids),
                           use_cache=False).logits[0, -1].float()
            if not torch.isfinite(logits).all():
                return {"status": "non_finite_logits", "next_token_entropy_nats": None,
                        "reference_perplexity": None}
            logp = torch.log_softmax(logits, -1)
            entropy.append(float(-(logp.exp() * logp).sum().item()))
        negative_log_likelihoods = []
        for prompt, reference in references:
            first = text_tensor(tokenizer, prompt, torch.device("cpu"))[0]
            completion_tokens = tokenizer.encode(reference, add_special_tokens=False)[:32]
            if not completion_tokens:
                continue
            suffix = torch.tensor(completion_tokens, dtype=torch.long)
            ids = torch.cat((first, suffix))[None, :]
            logits = model(input_ids=ids, attention_mask=torch.ones_like(ids),
                           use_cache=False).logits[0, len(first)-1:-1].float()
            if not torch.isfinite(logits).all():
                return {"status": "non_finite_logits", "next_token_entropy_nats": None,
                        "reference_perplexity": None}
            nll = -torch.log_softmax(logits, -1).gather(-1, suffix[:, None]).squeeze(-1)
            negative_log_likelihoods.extend(nll.tolist())
    if not negative_log_likelihoods:
        raise ValueError("No reference completion tokens")
    mean_nll = sum(negative_log_likelihoods) / len(negative_log_likelihoods)
    return {"status": "finite", "entropy_prompt_count": len(prompts),
            "next_token_entropy_nats": sum(entropy)/len(entropy),
            "reference_token_count": len(negative_log_likelihoods),
            "reference_perplexity": math.exp(min(mean_nll, 700)),
            "mean_reference_nll_nats": mean_nll}


def evaluate(model, tokenizer, device, holdout, baseline, args):
    from .fusion_validation import summarize
    from .rome_batch import generate_batches, parallel_execution

    completions = generate_batches(model, tokenizer, holdout, device=device,
                                   batch_size=args.batch_size, max_new_tokens=160)
    tests = parallel_execution(holdout, completions, workers=args.workers, timeout=4)
    score, cases = summarize(holdout, [row["completion"] for row in baseline],
                             [{"passed": row["passed"], "error": row["error"]} for row in baseline],
                             completions, tests)
    return score, cases


def run(args):
    import torch
    from safetensors.torch import save_file
    from .fusion_validation import archived_baseline, base_model_and_tokenizer, contiguous_tasks
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .weight_space import target_linear

    torch.set_num_threads(4)
    torch.manual_seed(0)
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Output dir contains previous experiment results")
    out.mkdir(parents=True, exist_ok=True)
    problems = fetch_problems()
    archive = json.loads(Path(args.source_archive).read_text(encoding="utf-8"))
    progress = json.loads(Path(args.source_progress).read_text(encoding="utf-8"))
    source = select_fifty(problems, archive, progress)
    holdout = contiguous_tasks(problems, START, STOP-START)
    baseline = archived_baseline(Path(args.baseline_previous), Path(args.baseline_final))
    if [row["task_id"] for row in baseline] != [x["task_id"] for x in holdout]:
        raise RuntimeError("Historical baseline mismatches benchmark task IDs")
    target_layers = ([(layer, "mlp.down_proj") for layer in STRESS_LAYERS]
                     if args.track == "stress" else list(RANK32_TARGETS))
    model, tokenizer, device = base_model_and_tokenizer()
    source_keys, reference_keys = collect_pairs(model, tokenizer, source, target_layers)
    factors = {}
    norms = {}
    base_factors = {}
    for layer, matrix in target_layers:
        name = target_name(layer, matrix)
        linear = target_linear(model, layer, matrix)
        left, right, metadata = multi_key_ridge(
            linear.weight, source_keys[name], reference_keys[name],
            rank=RANK if args.track == "rank32" else None)
        norms[name] = metadata
        base_factors[(layer, matrix)] = (left, right)

    prompt_probes = [x["prompt"] for x in holdout[:12]]
    perplexity_probes = [(x["prompt"], x["canonical_solution"]) for x in source[:8]]
    base_diagnostic = probe(model, tokenizer, prompt_probes, perplexity_probes)
    if base_diagnostic["status"] != "finite":
        raise RuntimeError("Baseline probe logits not finite")
    levels = ((args.stress_level / 100,) if args.track == "stress" and args.stress_level
              else STRESS_LEVELS if args.track == "stress" else (None,))
    variants, predictions = {}, {}
    for level in levels:
        variant = f"{level:.0%}" if level is not None else "rank32"
        print(f"Session011 {args.track} variant {variant}", flush=True)
        originals = {}
        layer_stats = {}
        stable = True
        try:
            for (layer, matrix), (left, right) in base_factors.items():
                label = target_name(layer, matrix)
                if level is not None:
                    left, right, scale = scaled_factors(
                        left, right, target_linear(model, layer, matrix).weight, level)
                else:
                    scale = 1.0
                key = f"{variant}.{label}"
                # safetensors disallows memory-aliased tensors under different
                # keys: each stored factor must own its backing storage.
                factors[f"{key}.left"] = left.cpu().contiguous().clone()
                factors[f"{key}.right"] = right.cpu().contiguous().clone()
                module = target_linear(model, layer, matrix)
                before, observed, finite = apply_factors(module, left, right)
                originals[(layer, matrix)] = before
                if level is not None and abs(observed - level) > 0.00005:
                    raise RuntimeError(f"Observed {label} norm {observed} differs from stress level {level}")
                layer_stats[label] = {"observed_relative_frobenius_norm": observed,
                                      "factor_scale": scale, "finite_weights": finite}
                stable &= finite
            if not stable:
                diagnostics = {"status": "non_finite_weights", "reference_perplexity": None,
                               "next_token_entropy_nats": None}
            else:
                diagnostics = probe(model, tokenizer, prompt_probes, perplexity_probes)
                stable = diagnostics["status"] == "finite"
            summary, cases, execution_failure = None, None, None
            if stable:
                try:
                    summary, cases = evaluate(model, tokenizer, device, holdout, baseline, args)
                    predictions[variant] = cases
                except (RuntimeError, ValueError, OverflowError) as exc:
                    # A large stress edit may produce finite prompt logits but
                    # fail later in greedy decoding. Do not invent a zero score.
                    execution_failure = f"{type(exc).__name__}: {str(exc)[:500]}"
                    stable = False
            ratio = (diagnostics["reference_perplexity"] / base_diagnostic["reference_perplexity"]
                     if diagnostics["reference_perplexity"] is not None else None)
            variants[variant] = {
                "status": "completed" if stable else "generation_failure" if execution_failure else "numerical_breakdown",
                "relative_norm_target": level, "layer_changes": layer_stats,
                "diagnostics": diagnostics, "perplexity_ratio_to_baseline": ratio,
                "perplexity_spike_ge_2x": ratio >= 2 if ratio is not None else None,
                "generation_error": execution_failure,
                "execution": summary,
                "observed_breakdown": {
                    "non_finite_weights_or_logits": diagnostics["status"] != "finite",
                    "lost_both_original_passing_tasks":
                        len(set(summary["passed_ids_before"]) & set(summary["passed_ids_after"])) == 0
                        if summary is not None else None,
                },
            }
            save_json(out / "progress.json", {"track": args.track,
                      "completed_variants": list(variants), "source_count": SOURCE_COUNT})
            save_json(out / "unbounded_predictions.json", {
                "task_ids": [x["task_id"] for x in holdout], "variants": predictions})
            save_json(out / "checkpoint_metrics.json", {
                "track": args.track, "completed_variants": variants,
                "source_failure_ids": [x["task_id"] for x in source]})
        finally:
            restore(model, originals)

    factor_name = ("unbounded_surgery_factors.safetensors" if args.track == "stress"
                   else "rank32_surgery_factors.safetensors")
    save_file({key: value.clone() for key, value in factors.items()}, str(out / factor_name))
    save_json(out / "unbounded_predictions.json", {"task_ids": [x["task_id"] for x in holdout],
                                                 "variants": predictions})
    from .branch_experiments import syntax_counts
    baseline_syntax = syntax_counts(holdout, [x["completion"] for x in baseline])
    report = {
        "status": "completed", "session": "011", "track": args.track,
        "branch": ("exp/08-unbounded-norm" if args.track == "stress" else "exp/09-rank32-surgery"),
        "base_model": BASE_MODEL, "dataset": DATA_URL, "device": "cpu", "threads": 4,
        "source_failure_ids": [x["task_id"] for x in source],
        "source_description": "Four original verified failures below 44, plus 46 archived failing baseline predictions from 44..93; source-reference set disjoint from 94..163",
        "source_archive_sha256": hashlib.sha256(Path(args.source_archive).read_bytes()).hexdigest(),
        "benchmark_ids": [x["task_id"] for x in holdout],
        "benchmark_status": "REUSED, exploratory; HumanEval/94–163 already consulted in Sessions 007–010",
        "baseline": {
            "passed_task_ids": [x["task_id"] for x in baseline if x["passed"]],
            "pass_at_1": sum(x["passed"] for x in baseline) / len(baseline),
            "pass_count": sum(x["passed"] for x in baseline),
            "ast_valid_count": baseline_syntax["valid"],
            "diagnostics": base_diagnostic,
        },
        "rank_per_matrix": SOURCE_COUNT if args.track == "stress" else RANK,
        "targets": [{"layer": layer, "matrix": matrix} for layer, matrix in target_layers],
        "factor_method": "50-key ridge closed-form W(T-K)(K^T K + lambda I)^-1 K^T; rank32 via thin QR/SVD",
        "uncapped_factor_stats": norms, "variants": variants,
        "reversible_factors": f"experiments/{factor_name}",
        "task_predictions": "experiments/unbounded_predictions.json",
        "no_training": True,
        "limits": "Three discrete norms cannot establish an exact continuous failure boundary. Teacher final-token activations do not prove semantic causation. Entropy is next-token at 12 fixed prompt endings; perplexity on first 32 reference tokens of 8 source examples. Syntax validity measured with ast.parse, separately from sandboxed execution.",
    }
    save_json(out / "unbounded_report.json", report)
    print("SESSION011", args.track, [(k, v["status"],
          None if v["execution"] is None else v["execution"]["after_passes"])
          for k, v in variants.items()], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", choices=("stress", "rank32"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-archive", default="experiments/rome_batch_predictions.json")
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--baseline-previous", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--baseline-final", default="experiments/final_holdout_validation_predictions.json")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--stress-level", type=int, choices=(15, 30, 50),
                        help="Isolate one stress level on a separate CPU runner")
    args = parser.parse_args()
    if not (1 <= args.batch_size <= 8 and 1 <= args.workers <= 8):
        parser.error("batch size and sandbox workers must be 1..8")
    if args.stress_level and args.track != "stress":
        parser.error("--stress-level only applies to the stress track")
    from .sandbox_eval import require_sandbox
    require_sandbox()
    run(args)


if __name__ == "__main__":
    main()
