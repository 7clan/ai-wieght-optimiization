"""Session 012: 0.5B-only dynamic hooks and multi-position rank-64 surgery.

This is an exploratory, gradient-free intervention. HumanEval/94..163 was
already consulted in earlier sessions and is not an independent holdout.
All model-produced code is executed solely in restricted Docker containers.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path

START, COUNT = 94, 70
SOURCE_COUNT = 50
TOKEN_POSITIONS = (-2, -1)
RANK = 64
LAYERS = ((8, "mlp.down_proj"), (13, "self_attn.o_proj"), (15, "self_attn.o_proj"))
HOOK_LAYERS = (13, 15)
OPERATORS = ("for", "while", "if", "return", "def", "range")
ALPHAS = (0.5, 1.0, 1.75, 2.5)


def select_sources(problems, archive, progress):
    """Freeze the 50 previously archived, genuinely failed pre-94 references."""
    from .rome20 import BASE_MODEL, DATA_URL

    rows = archive["holdout_records"]
    if ([r["task_id"] for r in rows] != [f"HumanEval/{i}" for i in range(44, 94)]
            or progress["base_model"] != BASE_MODEL or progress["source"] != DATA_URL):
        raise ValueError("Source archive provenance/order mismatch")
    original = progress["selected_failing_ids"]
    failures = [r["task_id"] for r in rows if r["before_passed"] is False]
    if len(original) != 20 or len(failures) != 46:
        raise ValueError("Expected 20 original failures and 46 baseline 44..93 failures")
    ids = original[:4] + failures
    if len(ids) != SOURCE_COUNT or len(set(ids)) != SOURCE_COUNT or any(
            int(i.rsplit("/", 1)[1]) >= START for i in ids):
        raise ValueError("Source examples leak the evaluation set")
    lookup = {p["task_id"]: p for p in problems}
    return [lookup[i] for i in ids]


def capture_positions(model, tokenizer, source, targets=LAYERS):
    """Two last input activations per source: 100 columns from 50 pairs.

    Cross-position teacher activations are *proxies* for correct behavior, not
    token-aligned causal mediators. This explicitly extends the old 50-key
    protocol because 50 columns mathematically cannot support rank 64.
    """
    import torch
    from .rome20 import text_tensor
    from .weight_space import target_linear

    failed = {key: [] for key in targets}
    teacher = {key: [] for key in targets}
    residual = {layer: {"failed": [], "teacher": []} for layer in HOOK_LAYERS}

    def run_text(content):
        captures, res, handles = {}, {}, []
        for target in targets:
            def save_proj(_m, inputs, _out, target=target):
                captures[target] = inputs[0][0, -2:].detach().float().cpu().clone()
            handles.append(target_linear(model, *target).register_forward_hook(save_proj))
        for layer in HOOK_LAYERS:
            def save_res(_m, _inp, output, layer=layer):
                hidden = output[0] if isinstance(output, tuple) else output
                res[layer] = hidden[0, -2:].detach().float().cpu().clone()
            handles.append(model.model.layers[layer].register_forward_hook(save_res))
        try:
            ids = text_tensor(tokenizer, content, torch.device("cpu"))
            if ids.shape[1] < 2:
                raise ValueError("Source text must contain at least two tokens")
            with torch.inference_mode():
                model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False)
        finally:
            for handle in handles:
                handle.remove()
        if set(captures) != set(targets) or set(res) != set(HOOK_LAYERS):
            raise RuntimeError("Activation capture incomplete")
        return captures, res

    for index, p in enumerate(source, 1):
        before, before_res = run_text(p["prompt"])
        after, after_res = run_text(p["prompt"] + p["canonical_solution"])
        for target in targets:
            failed[target].extend(before[target][j] for j in range(2))
            teacher[target].extend(after[target][j] for j in range(2))
        for layer in HOOK_LAYERS:
            residual[layer]["failed"].append(before_res[layer][-1])
            residual[layer]["teacher"].append(after_res[layer][-1])
        print(f"  paired source {index}/{SOURCE_COUNT}", flush=True)
    return failed, teacher, residual


def derive_rank64(weight, failures, teachers):
    """Closed-form 100-key ridge direction, truncated to rank 64 by thin QR/SVD."""
    import torch

    w = weight.detach().float().cpu()
    k = torch.stack(failures, dim=1).float().cpu()
    t = torch.stack(teachers, dim=1).float().cpu()
    expected = (w.shape[1], SOURCE_COUNT * len(TOKEN_POSITIONS))
    if k.shape != expected or t.shape != expected:
        raise ValueError("Expected exactly 100 paired input-state columns")
    gram = k.T @ k
    ridge = max(float(gram.diag().mean()) * 1e-4, 1e-4)
    residual = w @ (t - k)
    left_full = torch.linalg.solve(gram + ridge * torch.eye(k.shape[1]), residual.T).T
    qu, ru = torch.linalg.qr(left_full, mode="reduced")
    qv, rv = torch.linalg.qr(k, mode="reduced")
    u, s, vh = torch.linalg.svd(ru @ rv.T, full_matrices=False)
    threshold = max(float(s[0].item()) * 1e-6, 1e-7)
    numerical_rank = int((s > threshold).sum().item())
    if numerical_rank < RANK:
        raise RuntimeError(f"Observed numerical rank {numerical_rank} < requested {RANK}")
    root = s[:RANK].clamp_min(0).sqrt()
    left = ((qu @ u[:, :RANK]) * root[None, :]).contiguous()
    right = (root[:, None] * (vh[:RANK, :] @ qv.T)).contiguous()
    ratio = float((torch.linalg.vector_norm(left @ right) / torch.linalg.vector_norm(w)).item())
    if not all(torch.isfinite(x).all() for x in (left, right)) or not math.isfinite(ratio):
        raise RuntimeError("Non-finite rank64 factors")
    return left, right, {"observed_numerical_rank": numerical_rank, "applied_rank": RANK,
                         "ridge": ridge, "relative_delta_norm": ratio,
                         "singular_values_first_64": s[:RANK].tolist(),
                         "source_columns": k.shape[1]}


def logic_vectors(residual):
    """Average teacher-minus-failure decoder residual; correlation proxy only."""
    import torch

    vectors, metadata = {}, {}
    for layer in HOOK_LAYERS:
        pairs = residual[layer]
        diff = torch.stack(pairs["teacher"]) - torch.stack(pairs["failed"])
        direction = diff.mean(dim=0).float().contiguous()
        norm = float(torch.linalg.vector_norm(direction).item())
        if not math.isfinite(norm) or norm < 1e-6:
            raise RuntimeError(f"Degenerate residual reference direction at layer {layer}")
        vectors[layer] = (direction / norm).contiguous()
        metadata[str(layer)] = {"raw_difference_norm": norm, "unit_norm": True,
                                "pair_count": len(pairs["failed"])}
    return vectors, metadata


def archived_anchor(previous_file, final_file):
    """Previously evaluated 10% anchor on the same 70 reused tasks."""
    previous = json.loads(Path(previous_file).read_text(encoding="utf-8"))
    final = json.loads(Path(final_file).read_text(encoding="utf-8"))
    cases = previous["variants"]["10%"] + final["memit_10"]
    if [r["task_id"] for r in cases] != [f"HumanEval/{i}" for i in range(START, START+COUNT)]:
        raise ValueError("Archived anchor predictions are incomplete or out of order")
    return cases


class ConditionalResidualHooks:
    """Generate-time operator triggers, exact tensor-preserving decoder hooks."""

    def __init__(self, model, tokenizer, vectors):
        import torch

        self.model, self.tokenizer, self.vectors = model, tokenizer, vectors
        self.enabled = False
        self.alpha = 0.0
        self.mask = None
        self.handles = []
        self.layer_hits = Counter()
        self.operator_hits = Counter()
        self.ids = {}
        for operator in OPERATORS:
            operator_ids = set()
            for form in (operator, " " + operator, "\n" + operator):
                tokens = tokenizer.encode(form, add_special_tokens=False)
                if len(tokens) == 1 and tokenizer.decode(tokens).strip() == operator:
                    operator_ids.add(tokens[0])
            if not operator_ids:
                raise ValueError(f"No isolated vocabulary token available for {operator!r}")
            for token_id in operator_ids:
                self.ids[token_id] = operator
        self.trigger_ids = torch.tensor(sorted(self.ids), dtype=torch.long)

        def prehook(_module, args, kwargs):
            ids = kwargs.get("input_ids")
            if ids is None and args:
                ids = args[0]
            self.mask = None
            if self.enabled and ids is not None and ids.ndim == 2 and ids.shape[1] == 1:
                self.mask = torch.isin(ids, self.trigger_ids.to(ids.device))
                for token_id in ids[self.mask].flatten().tolist():
                    self.operator_hits[self.ids[int(token_id)]] += 1
            return None

        self.handles.append(model.register_forward_pre_hook(prehook, with_kwargs=True))
        for layer in HOOK_LAYERS:
            def hook(_module, _inputs, output, layer=layer):
                if not self.enabled or self.mask is None or not bool(self.mask.any()):
                    return output
                hidden = output[0] if isinstance(output, tuple) else output
                if hidden.ndim != 3 or hidden.shape[:2] != self.mask.shape:
                    raise RuntimeError(f"Layer {layer} residual/active-token shape mismatch")
                updated = hidden + (self.alpha * self.mask.unsqueeze(-1)
                                    * self.vectors[layer].to(hidden.device, hidden.dtype))
                if not torch.isfinite(updated).all():
                    raise RuntimeError(f"Non-finite residual at layer {layer}")
                self.layer_hits[layer] += int(self.mask.sum().item())
                return (updated, *output[1:]) if isinstance(output, tuple) else updated
            self.handles.append(model.model.layers[layer].register_forward_hook(hook))

    def reset(self, alpha):
        self.alpha = float(alpha)
        self.layer_hits.clear()
        self.operator_hits.clear()

    def stats(self):
        return {"alpha": self.alpha, "layer_trigger_counts": dict(self.layer_hits),
                "operator_token_counts": dict(self.operator_hits),
                "token_ids": {str(key): value for key, value in self.ids.items()},
                "generation_only": "Hooks activate on one-token cached decoder steps; prompt prefill bypassed"}

    def close(self):
        for handle in self.handles:
            handle.remove()


def dynamic_probe(model, tokenizer, source, hooks=None, alpha=0.0):
    """Reference perplexity and sampled generation-time next-token entropy.

    Uses the same autoregressive one-token cache steps that activate hooks.
    Every probe is fixed *before* evaluation and derives from pre-94 sources.
    """
    import torch
    from .rome20 import text_tensor

    nlls, entropies = [], []
    enabled_prior = hooks.enabled if hooks is not None else False
    if hooks is not None:
        hooks.reset(alpha)
        hooks.enabled = True
    try:
        with torch.inference_mode():
            for p in source[:6]:
                prefix = text_tensor(tokenizer, p["prompt"], torch.device("cpu"))
                continuation = tokenizer.encode(p["canonical_solution"], add_special_tokens=False)[:24]
                # Prefill is unchanged; on subsequent cached steps the previous
                # reference token is checked by the runtime pre-hook.
                output = model(input_ids=prefix, use_cache=True)
                logits, cache = output.logits[:, -1, :].float(), output.past_key_values
                for token in continuation:
                    if not torch.isfinite(logits).all():
                        return {"status": "non_finite", "token_perplexity": None,
                                "token_entropy_nats": None}
                    logp = torch.log_softmax(logits, -1)
                    entropies.append(float((-(logp.exp() * logp).sum(-1)).item()))
                    nlls.append(float((-logp[0, token]).item()))
                    next_id = torch.tensor([[token]], dtype=torch.long)
                    output = model(input_ids=next_id, past_key_values=cache, use_cache=True)
                    logits, cache = output.logits[:, -1, :].float(), output.past_key_values
    finally:
        if hooks is not None:
            hooks.enabled = enabled_prior
    if not nlls:
        raise ValueError("Reference perplexity probe contained no tokens")
    mean = sum(nlls) / len(nlls)
    return {"status": "finite", "reference_token_count": len(nlls),
            "token_perplexity": math.exp(min(mean, 700)),
            "mean_reference_nll_nats": mean,
            "token_entropy_nats": sum(entropies) / len(entropies),
            "entropy_sample_tokens": len(entropies),
            "source_probe_count": min(6, len(source))}


def conservative_taxonomy(problems, records, *, workers=4):
    """Four evidence labels plus unclassified, via restricted Docker diagnostics."""
    from .sandbox_eval import docker_command
    import os
    import re
    import subprocess
    import tempfile
    import uuid

    lookup = {p["task_id"]: p for p in problems}
    failing = []
    for record in records:
        problem = lookup[record["task_id"]]
        if record["after_passed"]:
            continue
        try:
            ast.parse(problem["prompt"] + record["after_completion"])
        except SyntaxError:
            continue
        failing.append((problem, record))

    def diagnose(item):
        problem, record = item
        code = (problem["prompt"] + record["after_completion"] + "\n\n"
                + problem["test"] + "\n\ncheck(globals()["
                + repr(problem["entry_point"]) + "])\n")
        with tempfile.TemporaryDirectory(prefix="tinycoder_overdrive_") as directory:
            os.chmod(directory, 0o755)
            script = Path(directory) / "solution.py"
            script.write_text(code, encoding="utf-8")
            os.chmod(script, 0o644)
            name = "overdrive-" + uuid.uuid4().hex[:12]
            try:
                result = subprocess.run(docker_command(directory, name), capture_output=True,
                                        timeout=8, check=False)
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                               timeout=10, check=False)
                return {"task_id": problem["task_id"], "category": "truncation_or_context",
                        "evidence": "sandbox timeout", "certainty": "observed"}
            if result.returncode == 125:
                raise RuntimeError("Docker sandbox refused the diagnostic replay")
            stderr = result.stderr.decode(errors="replace")
            exception = re.findall(r"(?m)^([A-Za-z_]+(?:Error|Exception))(?::|$)", stderr)
            exception = exception[-1] if exception else None
            if exception == "IndexError":
                category, evidence = "off_by_one_index_boundary", "Observed IndexError"
            elif exception == "TypeError":
                category, evidence = "wrong_output_type", "Observed TypeError; exact output mismatch not established"
            elif result.returncode != 0 and record["after_completion"].rstrip().endswith(("pass", "#")):
                category, evidence = "truncation_or_context", "Likely incomplete implementation; context expiry not established"
            else:
                category, evidence = "unclassified", "No direct evidence for one of four hypotheses"
            return {"task_id": problem["task_id"], "category": category,
                    "evidence": evidence, "certainty": "observed" if exception else "heuristic"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        details = list(pool.map(diagnose, failing))
    bins = ("off_by_one_index_boundary", "wrong_output_type", "missing_edge_case",
            "truncation_or_context", "unclassified")
    counts = Counter(record["category"] for record in details)
    return {"n_syntax_valid_failed": len(failing),
            "bins": {name: {"count": counts[name], "task_ids": [row["task_id"]
                                for row in details if row["category"] == name]} for name in bins},
            "cases": details,
            "limitations": "TypeError is not proof of wrong return type. Missing edge cases require witnessed inputs; absent direct evidence, cases remain unclassified."}


def main_run(args):
    import torch
    from safetensors.torch import save_file
    from .fusion_validation import (apply_reversible, archived_baseline,
                                    base_model_and_tokenizer, contiguous_tasks,
                                    summarize, tensor_factors)
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .rome_batch import generate_batches, parallel_execution
    from .weight_space import target_linear

    torch.manual_seed(0)
    torch.set_num_threads(4)
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite previous experiment outputs")
    out.mkdir(parents=True, exist_ok=True)
    problems = fetch_problems()
    evaluation = contiguous_tasks(problems, START, COUNT)
    archive_path, progress_path = Path(args.source_archive), Path(args.source_progress)
    source = select_sources(problems, json.loads(archive_path.read_text()),
                            json.loads(progress_path.read_text()))
    baseline = archived_baseline(Path(args.baseline_previous), Path(args.baseline_final))
    anchor_history = archived_anchor(args.baseline_previous, args.baseline_final)
    if [x["task_id"] for x in baseline] != [x["task_id"] for x in evaluation]:
        raise ValueError("Archived baseline task IDs inconsistent with pinned benchmark")
    before_completions = [x["completion"] for x in baseline]
    before_tests = [{"passed": x["passed"], "error": x["error"]} for x in baseline]
    model, tokenizer, device = base_model_and_tokenizer()
    baseline_diagnostics = dynamic_probe(model, tokenizer, source)
    down = target_linear(model, 8, "mlp.down_proj")
    anchor = tensor_factors(Path(args.anchor_factors), ("10%.layer8.left", "10%.layer8.right"))
    factor_sha = hashlib.sha256(Path(args.anchor_factors).read_bytes()).hexdigest()
    applied_anchor = apply_reversible(down, *anchor, expected_change=0.10)
    print("Verified exact archived Layer8 10% anchor", applied_anchor, flush=True)
    anchor_diagnostics = dynamic_probe(model, tokenizer, source)
    # The source activations are captured on the anchored model for both tracks.
    failure, teacher, residual = capture_positions(model, tokenizer, source)
    vectors, vector_info = logic_vectors(residual)
    factors = {"anchor.layer8.left": anchor[0], "anchor.layer8.right": anchor[1]}
    for layer, vec in vectors.items():
        factors[f"hook.layer{layer}.v_logic"] = vec
    rank_factors, matrix_info = {}, {}
    if args.track == "surgery":
        for target in LAYERS:
            left, right, info = derive_rank64(target_linear(model, *target).weight,
                                              failure[target], teacher[target])
            rank_factors[target] = (left, right)
            key = f"rank64.layer{target[0]}.{target[1].replace('.', '_')}"
            factors[f"{key}.left"] = left
            factors[f"{key}.right"] = right
            matrix_info[key] = info
        for target, (left, right) in rank_factors.items():
            module = target_linear(model, *target)
            with torch.no_grad():
                module.weight.add_((left @ right).to(module.weight.dtype))
            if not torch.isfinite(module.weight).all():
                raise RuntimeError(f"Non-finite surgery weight at {target}")
    save_file({k: v.detach().cpu().contiguous().clone() for k, v in factors.items()},
              str(out / "session012_extreme_factors.safetensors"))

    hooks = ConditionalResidualHooks(model, tokenizer, vectors)
    variants, predictions = {}, {}
    variant_list = (([(f"hooks_alpha_{a:g}", a) for a in ALPHAS]) if args.track == "hooks"
                    else [("rank64_static", None)] + [(f"rank64_hooks_alpha_{a:g}", a) for a in ALPHAS])
    try:
        for variant, alpha in variant_list:
            hooks.reset(alpha or 0.0)
            hooks.enabled = alpha is not None
            print(f"SESSION012 {args.track} {variant}", flush=True)
            try:
                metrics = dynamic_probe(model, tokenizer, source, hooks if hooks.enabled else None,
                                        alpha or 0.0)
            except (RuntimeError, ValueError, OverflowError) as exc:
                metrics = {"status": "probe_error", "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                           "token_perplexity": None, "token_entropy_nats": None}
            # Dynamic probe increments counters. Generation hits are logged alone.
            hooks.reset(alpha or 0.0)
            if metrics["status"] != "finite":
                variants[variant] = {"status": "probe_failed", "diagnostics": metrics,
                                     "execution": None, "taxonomy": None}
                continue
            try:
                completions = generate_batches(model, tokenizer, evaluation, device=device,
                                               batch_size=args.batch_size, max_new_tokens=160)
            except (RuntimeError, ValueError, OverflowError) as exc:
                variants[variant] = {"status": "generation_failed", "diagnostics": metrics,
                                     "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                                     "execution": None, "taxonomy": None}
                hooks.enabled = False
                continue
            hook_counts = hooks.stats()
            hooks.enabled = False
            tests = parallel_execution(evaluation, completions, workers=args.workers, timeout=4)
            summary, records = summarize(evaluation, before_completions, before_tests,
                                         completions, tests)
            taxonomy = conservative_taxonomy(evaluation, records, workers=args.workers)
            variants[variant] = {"status": "completed", "diagnostics": metrics,
                                 "execution": summary, "hook_stats": hook_counts,
                                 "taxonomy": taxonomy}
            predictions[variant] = records
            save_json(out / "progress.json", {"completed_variants": list(variants),
                                               "track": args.track})
            save_json(out / "session012_extreme_predictions.json",
                      {"task_ids": [p["task_id"] for p in evaluation], "variants": predictions})
            save_json(out / "checkpoint_metrics.json", {"track": args.track,
                                                       "variants": variants})
    finally:
        hooks.close()

    completed = [(name, value) for name, value in variants.items() if value["status"] == "completed"]
    best = max(completed, key=lambda row: row[1]["execution"]["after_passes"]) if completed else None
    entropy_base = anchor_diagnostics["token_entropy_nats"]
    entropy_spikes = [name for name, row in variants.items()
                      if row["status"] == "completed" and entropy_base is not None
                      and row["diagnostics"]["token_entropy_nats"] >= 2 * entropy_base]
    first_spike_alpha = next((a for a in ALPHAS if any(
        name.endswith(f"alpha_{a:g}") for name in entropy_spikes)), None)
    report = {
        "status": "completed" if len(completed) == len(variant_list) else "partial",
        "session": "012", "branch": "exp/10-extreme-overdrive", "track": args.track,
        "base_model": BASE_MODEL, "dataset": DATA_URL, "model_size_unchanged": True,
        "device": "cpu", "threads": torch.get_num_threads(), "decode": "greedy, 160 new tokens",
        "source_failure_ids": [p["task_id"] for p in source],
        "source_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "source_column_method": "Exactly two last token positions per each of 50 frozen pre-94 failure/reference pairs; 100 keys, up to rank100. Teacher positions are unaligned proxy targets.",
        "benchmark_ids": [p["task_id"] for p in evaluation],
        "benchmark_status": "REUSED, exploratory; HumanEval/94–163 consumed in earlier sessions",
        "baseline": {"pass_count": sum(x["passed"] for x in baseline),
                     "passed_ids": [x["task_id"] for x in baseline if x["passed"]],
                     "diagnostics": baseline_diagnostics},
        "anchor": {"matrix": "layer8.mlp.down_proj", "observed_relative_frobenius": applied_anchor,
                   "file_sha256": factor_sha, "factor_source_commit": "e100c628cd8fcf3c500e5c39070168e213b208aa",
                   "pass_count": sum(row["after_passed"] for row in anchor_history),
                   "passed_ids": [r["task_id"] for r in anchor_history if r["after_passed"]],
                   "diagnostics": anchor_diagnostics},
        "dynamic": {"operators": list(OPERATORS), "alphas": list(ALPHAS),
                    "layers": list(HOOK_LAYERS), "vector_method": "unit-normalized mean teacher-minus-failure residual vectors on 50 frozen pairs; not proven logic-circuit mediation",
                    "vector_info": vector_info, "best_discrete_variant": best[0] if best else None,
                    "entropy_spike_threshold": "2x unhooked 10% anchor's mean reference-token entropy (not proof of corruption)",
                    "discrete_entropy_spikes": entropy_spikes,
                    "first_sampled_spike_alpha": first_spike_alpha},
        "static_rank64": {"enabled": args.track == "surgery", "targets": [str(t) for t in LAYERS],
                          "matrix_stats": matrix_info, "rank": RANK if args.track == "surgery" else None},
        "variants": variants, "reversible_factors": "experiments/session012_extreme_factors.safetensors",
        "task_predictions": "experiments/session012_extreme_predictions.json", "no_training": True,
        "limits": "This sweep only finds a discrete best sampled alpha, not an exact global peak or absolute mathematical limit. Rank64 needs at least 64 linearly independent state columns, hence two positions per each source pair. Syntax is ast.parse validity; pass@1 is exact sandboxed assertions; error bins are diagnostic proxies, not verified root causes."}
    save_json(out / "session012_extreme_report.json", report)
    print("SESSION012 FINISHED", args.track, [(name, row["status"],
          row["execution"]["after_passes"] if row["execution"] else None)
          for name, row in variants.items()], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", choices=("hooks", "surgery"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-archive", default="experiments/rome_batch_predictions.json")
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--baseline-previous", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--baseline-final", default="experiments/final_holdout_validation_predictions.json")
    parser.add_argument("--anchor-factors", default="experiments/exp03_norm_break_factors.safetensors")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 8 or not 1 <= args.workers <= 8:
        parser.error("batch size/workers must each be 1..8")
    from .sandbox_eval import require_sandbox
    require_sandbox()
    main_run(args)


if __name__ == "__main__":
    main()
