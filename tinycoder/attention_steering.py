"""Session 009: head-resolved attention activation patching and rank-one edits.

Only the original 20 *failure-conditioned reference* prompts determine layer
and head targets. The previously used HumanEval/94–163 suite is held back
until both edits are frozen. This is a mechanistic proxy experiment, not a
demonstration of general coding improvement or a faithful ROME algorithm.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import platform
import statistics
from pathlib import Path

SOURCE_COMMIT = "e100c628cd8fcf3c500e5c39070168e213b208aa"
SCAN_LAYERS = tuple(range(10, 19))
EDITABLE_LAYERS = tuple(range(12, 17))
ATTENTION_CAP = 0.015
HEAD_BATCH = 4


def logic_labels(problem: dict) -> dict[str, bool]:
    """Explicit source-code *proxies*, not validated cognitive labels."""
    tree = ast.parse(problem["prompt"] + problem["canonical_solution"])
    counts = Counter(node.id for node in ast.walk(tree)
                     if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store))
    has_loop = any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))
    has_rewrite = any(isinstance(node, ast.AugAssign) for node in ast.walk(tree))
    return {"loop_state": has_loop,
            "variable_tracking": has_rewrite or any(count >= 2 for count in counts.values())}


def source_failures(problems, progress: dict) -> list[dict]:
    from .rome20 import BASE_MODEL, DATA_URL

    if progress.get("base_model") != BASE_MODEL or progress.get("source") != DATA_URL:
        raise ValueError("Historical failure example provenance mismatch")
    ids = progress.get("selected_failing_ids", [])
    if len(ids) != 20 or len(set(ids)) != 20 or any(int(x.split("/")[-1]) >= 94 for x in ids):
        raise ValueError("Must derive targets from exactly 20 original failures")
    lookup = {p["task_id"]: p for p in problems}
    if not all(x in lookup for x in ids):
        raise ValueError("Original failure references missing from pinned HumanEval")
    return [lookup[x] for x in ids]


def collect_attn(model, tokenizer, source: str, layers=SCAN_LAYERS):
    """Capture every o_proj input/output at last token in one forward pass."""
    import torch
    from .rome20 import text_tensor
    from .weight_space import target_linear

    captured = {}
    hooks = []
    for layer in layers:
        module = target_linear(model, layer, "self_attn.o_proj")

        def record(_module, inputs, output, target=layer):
            captured[target] = {
                "input": inputs[0][0, -1].detach().float().cpu().clone(),
                "output": output[0, -1].detach().float().cpu().clone(),
            }

        hooks.append(module.register_forward_hook(record))
    try:
        input_ids = text_tensor(tokenizer, source, next(model.parameters()).device)
        with torch.inference_mode():
            logits = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                           use_cache=False).logits[0, -1].detach().float().cpu()
    finally:
        for hook in hooks:
            hook.remove()
    if set(captured) != set(layers):
        raise RuntimeError("Attention activation capture missing requested layers")
    return captured, logits


def token_logprob(logits, token_id: int) -> float:
    import torch

    return float(torch.log_softmax(logits.float(), dim=-1)[token_id].item())


def full_output_patch(model, tokenizer, source, layer, replacement, token):
    """Real counterfactual forward pass, swapping one last-token projection."""
    import torch
    from .rome20 import text_tensor
    from .weight_space import target_linear

    module = target_linear(model, layer, "self_attn.o_proj")

    def replace(_module, _args, output):
        changed = output.clone()
        changed[:, -1, :] = replacement.to(dtype=changed.dtype, device=changed.device)
        return changed

    hook = module.register_forward_hook(replace)
    try:
        input_ids = text_tensor(tokenizer, source, module.weight.device)
        with torch.inference_mode():
            logits = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                           use_cache=False).logits[0, -1]
            return token_logprob(logits, token)
    finally:
        hook.remove()


def head_input_patch_batch(model, tokenizer, source, layer, reference_input,
                           heads, head_dim: int, token: int):
    """Patch a different o_proj *input head slice* in each parallel batch row."""
    import torch
    from .rome20 import text_tensor
    from .weight_space import target_linear

    if not heads or len(heads) > HEAD_BATCH or len(set(heads)) != len(heads):
        raise ValueError("Head intervention batch must contain 1–4 distinct heads")
    module = target_linear(model, layer, "self_attn.o_proj")
    if any(h < 0 or (h + 1) * head_dim > module.in_features for h in heads):
        raise ValueError("Head slice is outside attention projection input")

    def replace_inputs(_module, args):
        tensor = args[0].clone()
        for index, head in enumerate(heads):
            start = head * head_dim
            tensor[index, -1, start:start + head_dim] = reference_input[start:start + head_dim].to(
                dtype=tensor.dtype, device=tensor.device)
        return (tensor,)

    hook = module.register_forward_pre_hook(replace_inputs)
    try:
        base = text_tensor(tokenizer, source, module.weight.device)
        input_ids = base.repeat(len(heads), 1)
        with torch.inference_mode():
            logits = model(input_ids=input_ids, attention_mask=torch.ones_like(input_ids),
                           use_cache=False).logits[:, -1].float()
            values = torch.log_softmax(logits, dim=-1)[:, token].detach().cpu().tolist()
        return [float(x) for x in values]
    finally:
        hook.remove()


def category_mean(cases, values, category):
    selected = [value for item, value in zip(cases, values, strict=True)
                if item["labels"][category]]
    return statistics.mean(selected) if selected else None


def rank_layers(cases, full_effects):
    """Use category-balanced patched log-probability, only original 20 cases."""
    scores = []
    for layer in SCAN_LAYERS:
        values = full_effects[layer]
        loop = category_mean(cases, values, "loop_state")
        variable = category_mean(cases, values, "variable_tracking")
        if loop is None or variable is None:
            raise RuntimeError("No loop or repeated-variable reference tasks; cannot claim logic-specific tracing")
        scores.append({"layer": layer, "mean_delta_logprob": statistics.mean(values),
                       "loop_state_mean_delta": loop, "variable_tracking_mean_delta": variable,
                       "logic_balance_score": (loop + variable) / 2,
                       "positive_cases": sum(x > 0 for x in values), "cases": len(values)})
    editable = sorted((s for s in scores if s["layer"] in EDITABLE_LAYERS),
                      key=lambda s: (s["logic_balance_score"], s["mean_delta_logprob"]), reverse=True)
    return scores, editable[:2]


def select_causal_heads(cases, selected_layers, head_effects):
    """Assign one loop-oriented and one variable-oriented head to distinct layers."""
    categories = ("loop_state", "variable_tracking")
    if len(selected_layers) != 2 or selected_layers[0] == selected_layers[1]:
        raise ValueError("Need two different causal attention matrices")

    heads = {}
    for layer in selected_layers:
        by_category = {}
        for category in categories:
            ranked = [(head, category_mean(cases, head_effects[layer][head], category))
                      for head in sorted(head_effects[layer])]
            if any(score is None for _, score in ranked):
                raise ValueError("Cannot score logic subgroup with no samples")
            by_category[category] = max(ranked, key=lambda entry: (entry[1], -entry[0]))
        heads[layer] = by_category

    a, b = selected_layers
    direct = heads[a]["loop_state"][1] + heads[b]["variable_tracking"][1]
    swapped = heads[a]["variable_tracking"][1] + heads[b]["loop_state"][1]
    pairing = ((a, "loop_state"), (b, "variable_tracking")) if direct >= swapped else (
        (a, "variable_tracking"), (b, "loop_state"))
    return [{"layer": layer, "head": heads[layer][category][0], "category": category,
             "head_delta_logprob": heads[layer][category][1]}
            for layer, category in pairing]


def derive_head_rank_one(weight, failing_inputs, reference_inputs, head: int,
                         head_dim: int, *, cap: float = ATTENTION_CAP):
    """Exact ridge/Woodbury rank-one update, restricted to one head's columns."""
    import torch
    from .rome20 import ridge_inverse_times_key
    from .weight_space import cap_factors

    matrix = weight.detach().float().cpu()
    start, stop = head * head_dim, (head + 1) * head_dim
    if not 0 <= start < stop <= matrix.shape[1]:
        raise ValueError("Selected head slice does not fit o_proj weight")
    if len(failing_inputs) != len(reference_inputs) or len(failing_inputs) != 20:
        raise ValueError("Rank-one surgery requires exactly 20 paired reference vectors")
    keys = [value[start:stop].detach().float().cpu() for value in failing_inputs]
    target_keys = [value[start:stop].detach().float().cpu() for value in reference_inputs]
    k_bar, v_bar = torch.stack(keys).mean(0), torch.stack(target_keys).mean(0)
    inverse_key, ridge = ridge_inverse_times_key(keys, k_bar)
    denom = torch.dot(k_bar, inverse_key)
    if denom.item() <= 1e-10:
        raise ValueError("Unstable head-only rank-one denominator")
    target_delta = matrix[:, start:stop] @ (v_bar - k_bar)
    left = target_delta
    right = torch.zeros(matrix.shape[1], dtype=matrix.dtype)
    right[start:stop] = inverse_key / denom
    left, right, proposal, scale = cap_factors(matrix, left, right, cap)
    actual = float((torch.linalg.vector_norm(left) * torch.linalg.vector_norm(right)
                    / torch.linalg.vector_norm(matrix)).item())
    initial_distance = float(torch.linalg.vector_norm(target_delta).item())
    residual = float(torch.linalg.vector_norm(target_delta - left * torch.dot(right[start:stop], k_bar)).item())
    return left.contiguous(), right.contiguous(), {
        "selected_head": head, "head_input_columns": [start, stop - 1],
        "method": "ROME-style Woodbury centroid edit restricted to one output-projection head slice",
        "ridge": ridge, "rank": 1, "samples": len(keys),
        "target_contribution_distance_before": initial_distance,
        "target_contribution_distance_after": residual,
        "proposed_frobenius_delta": proposal, "cap_scale": scale,
        "expected_relative_frobenius_change": actual,
        "warning": "The teacher-forced last-token head state is a proxy for logic, not a proven semantic circuit",
    }


def select_and_edit(args):
    import torch
    from safetensors.torch import save_file
    from .fusion_validation import apply_reversible, base_model_and_tokenizer, tensor_factors
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .weight_space import apply_weight_edit, get_layer_weights, target_linear

    problems = fetch_problems()
    progress = json.loads(Path(args.source_progress).read_text(encoding="utf-8"))
    original_cases = source_failures(problems, progress)
    model, tokenizer, device = base_model_and_tokenizer()
    head_count = int(model.config.num_attention_heads)
    module = target_linear(model, 12, "self_attn.o_proj")
    if head_count < 2 or module.in_features % head_count:
        raise ValueError("Cannot separate attention o_proj input by model heads")
    head_dim = module.in_features // head_count

    cases = []
    for idx, problem in enumerate(original_cases, 1):
        labels = logic_labels(problem)
        ref_ids = tokenizer(problem["canonical_solution"], add_special_tokens=False)["input_ids"]
        if not ref_ids:
            raise ValueError("Reference completion has no next token")
        failure, logits = collect_attn(model, tokenizer, problem["prompt"])
        teacher, _ = collect_attn(model, tokenizer, problem["prompt"] + problem["canonical_solution"])
        cases.append({"task_id": problem["task_id"], "prompt": problem["prompt"],
                      "labels": labels, "token": ref_ids[0],
                      "base_logprob": token_logprob(logits, ref_ids[0]),
                      "failure": failure, "teacher": teacher})
        print(f"  original failure/reference attention capture {idx}/20", flush=True)

    counts = {name: sum(c["labels"][name] for c in cases)
              for name in ("loop_state", "variable_tracking")}
    if any(n < 2 for n in counts.values()):
        raise RuntimeError(f"Too few original tasks match required logic subgroups: {counts}")

    full_effects = {layer: [] for layer in SCAN_LAYERS}
    print("Causal full-output o_proj interventions across layers 10–18", flush=True)
    for index, case in enumerate(cases, 1):
        for layer in SCAN_LAYERS:
            patched = full_output_patch(model, tokenizer, case["prompt"], layer,
                                        case["teacher"][layer]["output"], case["token"])
            full_effects[layer].append(patched - case["base_logprob"])
        print(f"  full-projection patch {index}/20 x {len(SCAN_LAYERS)} layers", flush=True)
    layer_ranking, top_two = rank_layers(cases, full_effects)
    selected_layers = [s["layer"] for s in top_two]
    print(f"Top two within requested 12–16 editing window: {selected_layers}", flush=True)

    head_effects = {layer: {head: [] for head in range(head_count)} for layer in selected_layers}
    for idx, case in enumerate(cases, 1):
        for layer in selected_layers:
            for offset in range(0, head_count, HEAD_BATCH):
                heads = list(range(offset, min(offset + HEAD_BATCH, head_count)))
                patched = head_input_patch_batch(model, tokenizer, case["prompt"], layer,
                                                 case["teacher"][layer]["input"],
                                                 heads, head_dim, case["token"])
                for head, logprob in zip(heads, patched, strict=True):
                    head_effects[layer][head].append(logprob - case["base_logprob"])
        print(f"  selected-layer head intervention {idx}/20", flush=True)
    selected = select_causal_heads(cases, selected_layers, head_effects)

    factors = {}
    for choice in selected:
        layer, head = choice["layer"], choice["head"]
        target = target_linear(model, layer, "self_attn.o_proj")
        initial, stats_before = get_layer_weights(model, layer, "self_attn.o_proj")
        left, right, derived = derive_head_rank_one(
            initial, [c["failure"][layer]["input"] for c in cases],
            [c["teacher"][layer]["input"] for c in cases], head, head_dim)
        apply_weight_edit(model, layer, "self_attn.o_proj", left, right)
        actual = float((torch.linalg.vector_norm((target.weight - initial).float())
                        / torch.linalg.vector_norm(initial.float())).item())
        if actual > ATTENTION_CAP + 1e-6:
            with torch.no_grad():
                target.weight.copy_(initial)
            raise RuntimeError("Observed attention edit exceeded predeclared 1.5% cap")
        choice["edit"] = {**derived, "observed_relative_frobenius_change": actual,
                          "matrix_inspection_before": stats_before}
        factors[f"layer{layer}.self_attn_o_proj.left"] = left.detach().cpu().clone().contiguous()
        factors[f"layer{layer}.self_attn_o_proj.right"] = right.detach().cpu().clone().contiguous()

    stress_path = Path(args.stress_factors)
    left, right = tensor_factors(stress_path, ("10%.layer8.left", "10%.layer8.right"))
    observed_mlp = apply_reversible(target_linear(model, 8, "mlp.down_proj"),
                                    left, right, expected_change=.10)
    factors["layer8.mlp_down_proj.left"] = left.detach().cpu().clone().contiguous()
    factors["layer8.mlp_down_proj.right"] = right.detach().cpu().clone().contiguous()

    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    save_file(factors, str(destination / "attn_steering_factors.safetensors"))
    head_summary = {str(layer): [
        {"head": head, "all_mean_delta_logprob": statistics.mean(values),
         "loop_state_mean_delta": category_mean(cases, values, "loop_state"),
         "variable_tracking_mean_delta": category_mean(cases, values, "variable_tracking")}
        for head, values in sorted(head_effects[layer].items())]
        for layer in selected_layers}
    report = {"status": "traced_and_frozen", "session": "009", "source_commit": SOURCE_COMMIT,
              "base_model": BASE_MODEL, "dataset": DATA_URL,
              "reference_task_ids": [p["task_id"] for p in original_cases],
              "proxy_definitions": {"loop_state": "Reference function contains a for/while loop",
                                    "variable_tracking": "Reference function reassigns a name or uses augmented assignment"},
              "proxy_counts": counts,
              "proxy_task_ids": {category: [c["task_id"] for c in cases if c["labels"][category]]
                                 for category in counts},
              "causal_metric": "Change in log p(first canonical completion token) when patching last-token o_proj output or one input-head block",
              "attention_scan": layer_ranking,
              "selected_layers": selected_layers, "head_dim": head_dim,
              "head_count": head_count, "head_mediation": head_summary,
              "selected_head_edits": selected, "attention_norm_cap": ATTENTION_CAP,
              "archived_layer8_mlp_relative_norm": observed_mlp,
              "archived_mlp_sha256": hashlib.sha256(stress_path.read_bytes()).hexdigest(),
              "hardware": {"cpu_threads": torch.get_num_threads(), "python": platform.python_version()},
              "no_training": True,
              "limitations": "Head/logic associations use rough source AST categories and teacher-forced terminal activations; positive log-probability mediation does not prove correct variable/loop reasoning"}
    save_json(destination / "trace_report.json", report)
    print("TRACED", [(s["layer"], s["head"], s["category"]) for s in selected], flush=True)


def evaluate_frozen(args):
    import torch
    from safetensors.torch import load_file
    from .fusion_validation import (apply_reversible, archived_baseline,
                                    base_model_and_tokenizer, contiguous_tasks, summarize)
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .rome_batch import generate_batches, parallel_execution
    from .weight_space import target_linear

    trace = json.loads(Path(args.trace_report).read_text(encoding="utf-8"))
    if (trace.get("status") != "traced_and_frozen" or trace.get("source_commit") != SOURCE_COMMIT
            or trace.get("reference_task_ids") != json.loads(
                Path(args.source_progress).read_text(encoding="utf-8"))["selected_failing_ids"]
            or len(trace.get("selected_head_edits", [])) != 2):
        raise ValueError("Edited factors not from the completed original-20 causal trace")
    layers = [item["layer"] for item in trace["selected_head_edits"]]
    if len(set(layers)) != 2 or any(layer not in EDITABLE_LAYERS for layer in layers):
        raise ValueError("Selected attention layers violate 12–16 constraint")

    factors = load_file(str(args.trace_factors), device="cpu")
    model, tokenizer, device = base_model_and_tokenizer()
    actual = {}
    for entry in trace["selected_head_edits"]:
        layer = entry["layer"]
        actual[str(layer)] = apply_reversible(
            target_linear(model, layer, "self_attn.o_proj"),
            factors[f"layer{layer}.self_attn_o_proj.left"],
            factors[f"layer{layer}.self_attn_o_proj.right"],
            expected_change=entry["edit"]["observed_relative_frobenius_change"], tolerance=.00004)
    actual["8_mlp"] = apply_reversible(
        target_linear(model, 8, "mlp.down_proj"), factors["layer8.mlp_down_proj.left"],
        factors["layer8.mlp_down_proj.right"], expected_change=.10)

    problems = contiguous_tasks(fetch_problems(), 94, 70)
    baseline = archived_baseline(Path(args.previous_predictions), Path(args.validation_predictions))
    baseline_completions = [item["completion"] for item in baseline]
    baseline_tests = [{"passed": item["passed"], "error": item["error"]} for item in baseline]
    print("Frozen Layer 8 MEMIT + two rank-one attention projections: 70-task Docker evaluation", flush=True)
    after = generate_batches(model, tokenizer, problems, device=device,
                             batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    tests = parallel_execution(problems, after, workers=args.workers, timeout=args.exec_timeout)
    score, records = summarize(problems, baseline_completions, baseline_tests, after, tests)
    report = {"status": "completed", "session": "009", "branch": "exp/06-attn-steering",
              "source_commit": SOURCE_COMMIT, "base_model": BASE_MODEL, "dataset": DATA_URL,
              "reference_task_ids": trace["reference_task_ids"],
              "task_ids": [p["task_id"] for p in problems], "frozen_attention_layers": layers,
              "frozen_head_assignments": [{"layer": x["layer"], "head": x["head"],
                                           "category": x["category"]} for x in trace["selected_head_edits"]],
              "applied_relative_weight_norms": actual, "scores": score,
              "evaluation": {"execution": "70 Docker-isolated official HumanEval assertion sets",
                             "baseline": "50 archived Session007 + 20 archived Session008 baseline completions",
                             "syntax": "ast.parse(prompt + completion)"},
              "no_training": True,
              "caution": "All 70 tasks were used in prior model comparisons; this is exploratory, not independent validation"}
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    save_json(destination / "report.json", report)
    save_json(destination / "predictions.json", {"task_ids": report["task_ids"], "cases": records})
    print("ATTENTION STEERING PASS@1", score["before_passes"], "->", score["after_passes"], flush=True)


def main():
    parser = argparse.ArgumentParser(description="CPU causal head tracing and direct rank-one attention steering")
    parser.add_argument("--mode", required=True, choices=("trace", "evaluate"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--stress-factors", default="experiments/exp03_norm_break_factors.safetensors")
    parser.add_argument("--trace-report", default="frozen_trace/trace_report.json")
    parser.add_argument("--trace-factors", default="frozen_trace/attn_steering_factors.safetensors")
    parser.add_argument("--previous-predictions", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--validation-predictions", default="experiments/final_holdout_validation_predictions.json")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--exec-timeout", type=int, default=4)
    args = parser.parse_args()
    if not (1 <= args.batch_size <= 8 and 1 <= args.workers <= 8
            and 32 <= args.max_new_tokens <= 512 and 1 <= args.exec_timeout <= 30):
        parser.error("Invalid CPU generation or sandbox parameters")
    import torch
    from .sandbox_eval import require_sandbox
    require_sandbox()
    torch.set_num_threads(4)
    torch.manual_seed(0)
    destination = Path(args.output_dir)
    if any((destination / name).exists() for name in
           ("trace_report.json", "attn_steering_factors.safetensors", "report.json", "predictions.json")):
        raise FileExistsError("Refusing to overwrite a previous measured experiment")
    if args.mode == "trace":
        select_and_edit(args)
    else:
        evaluate_frozen(args)


if __name__ == "__main__":
    main()
