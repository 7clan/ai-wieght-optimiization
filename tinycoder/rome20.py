"""20-failure, gradient-free ROME-style weight-edit experiment on HumanEval.

Uses a pretrained BASE model, not the instruction-tuned model. Canonical code
solutions supply teacher-forced internal activations; nothing is fine-tuned.
This is not the full ROME algorithm: no optimized target value or causal trace
over all token positions, and covariance is estimated from only 20 keys.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
import urllib.request
from pathlib import Path

BASE_MODEL = "Qwen/Qwen2.5-Coder-0.5B"
DATA_COMMIT = "b9453e8f1865df0a0057a1383767caa400acfbcf"
DATA_URL = f"https://raw.githubusercontent.com/openai/human-eval/{DATA_COMMIT}/data/HumanEval.jsonl.gz"


def fetch_problems() -> list[dict]:
    """Read the pinned, original MIT-licensed OpenAI HumanEval test collection."""
    with urllib.request.urlopen(DATA_URL, timeout=35) as response:
        payload = response.read(2_000_000)
    records = [json.loads(line) for line in gzip.decompress(payload).decode("utf-8").splitlines() if line.strip()]
    if len(records) != 164 or any(not {"task_id", "prompt", "canonical_solution", "test", "entry_point"} <= x.keys()
                                  for x in records):
        raise ValueError("Unexpected HumanEval dataset; stopping instead of using mismatched tasks")
    return records


def text_tensor(tokenizer, text: str, device):
    import torch

    token_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if not token_ids:
        raise ValueError("Empty token sequence")
    return torch.tensor([token_ids], dtype=torch.long, device=device)


def generate_completion(model, tokenizer, prompt: str, max_new_tokens: int) -> str:
    import torch

    tensor = text_tensor(tokenizer, prompt, next(model.parameters()).device)
    with torch.inference_mode():
        result = model.generate(
            input_ids=tensor,
            attention_mask=torch.ones_like(tensor),
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(result[0, tensor.shape[1]:], skip_special_tokens=True)


def capture_layer_pairs(model, tokenizer, source: str):
    """Capture all down_proj input keys and output values at the last token."""
    import torch

    keys, values = {}, {}
    handles = []
    layers = model.model.layers
    for idx, block in enumerate(layers):
        def capture(_module, arguments, output, index=idx):
            keys[index] = arguments[0][0, -1].detach().float().cpu().clone()
            values[index] = output[0, -1].detach().float().cpu().clone()

        handles.append(block.mlp.down_proj.register_forward_hook(capture))
    try:
        tensor = text_tensor(tokenizer, source, next(model.parameters()).device)
        with torch.inference_mode():
            output = model(input_ids=tensor, attention_mask=torch.ones_like(tensor))
        logits = output.logits[0, -1].detach().float().cpu()
    finally:
        for handle in handles:
            handle.remove()
    if len(keys) != len(layers) or len(values) != len(layers):
        raise RuntimeError("Failed to observe all projection layers")
    return keys, values, logits


def patched_first_token_logprob(model, tokenizer, prompt: str, layer: int, value, token_id: int) -> float:
    """Causal intervention: replace one last-token MLP output, then observe log p(token)."""
    import torch

    module = model.model.layers[layer].mlp.down_proj

    def replace(_module, _inputs, output):
        patched = output.clone()
        patched[0, -1, :] = value.to(device=output.device, dtype=output.dtype)
        return patched

    handle = module.register_forward_hook(replace)
    try:
        tensor = text_tensor(tokenizer, prompt, module.weight.device)
        with torch.inference_mode():
            logits = model(input_ids=tensor, attention_mask=torch.ones_like(tensor)).logits[0, -1].float()
        return float(torch.log_softmax(logits, dim=-1)[token_id].item())
    finally:
        handle.remove()


def ridge_inverse_times_key(keys, key, ridge_fraction: float = 0.01):
    """Exact Woodbury inverse of C=λI + KKᵀ/n, without a giant d×d inverse."""
    import torch

    k_matrix = torch.stack(keys, dim=1).detach().double().cpu()  # d x n
    key = key.detach().double().cpu()
    if k_matrix.shape[0] != key.numel():
        raise ValueError("Invalid key dimensions")
    n = k_matrix.shape[1]
    u = k_matrix / math.sqrt(n)
    ridge = max(float(k_matrix.square().mean().item()) * ridge_fraction, 1e-5)
    small = ridge * torch.eye(n, dtype=torch.float64) + u.T @ u
    solved = torch.linalg.solve(small, u.T @ key)
    return ((key - u @ solved) / ridge).float(), ridge


def derive_average_rank_one(weight, failing_keys: list, successful_values: list,
                            max_relative_change: float, alpha: float = 1.0):
    """ROME-style closed form for the average of 20 *different* associations.

    One rank-one edit cannot generally satisfy all 20 pairs: their aggregate
    centroid is the single target. Report this limitation explicitly.
    """
    import torch
    from .weight_space import cap_factors

    if len(failing_keys) != len(successful_values) or not failing_keys:
        raise ValueError("Must provide matched key/value pairs")
    matrix = weight.detach().float().cpu()
    key_bar = torch.stack(failing_keys).mean(dim=0)
    target_bar = torch.stack(successful_values).mean(dim=0)
    inverse_key, ridge = ridge_inverse_times_key(failing_keys, key_bar)
    denominator = torch.dot(key_bar, inverse_key)
    if denominator.item() <= 1e-8:
        raise ValueError("Unstable rank-one denominator")
    left = alpha * (target_bar - matrix @ key_bar)
    right = inverse_key / denominator
    left, right, proposal, applied_scale = cap_factors(matrix, left, right, max_relative_change)
    before = float(torch.linalg.vector_norm(matrix @ key_bar - target_bar).item())
    after = float(torch.linalg.vector_norm((matrix + torch.outer(left, right)) @ key_bar - target_bar).item())
    return left, right, {
        "covariance": "ridge-plus-empirical-full-rank20 via Woodbury",
        "ridge": ridge,
        "centroid_distance_before": before,
        "centroid_distance_after": after,
        "proposed_delta_norm": proposal,
        "cap_scale": applied_scale,
        "actual_relative_delta_norm": float((torch.linalg.vector_norm(left) * torch.linalg.vector_norm(right)).item()
                                            / torch.linalg.vector_norm(matrix).item()),
        "warning": "A single rank-one update targets the centroid, not 20 exact associations",
    }


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(args):
    import torch
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .sandbox_eval import evaluate_completion, require_sandbox
    from .weight_space import apply_weight_edit, matrix_statistics

    require_sandbox()
    torch.set_num_threads(min(4, torch.get_num_threads()))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    model_name = BASE_MODEL
    print(f"Loading base model {model_name}, no adapters or training", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.float32).eval().to("cpu")
    problems = fetch_problems()

    selected, holdout, scanned = [], [], []
    print("Collecting 20 failed completions with Docker execution tests...", flush=True)
    for problem in problems:
        completion = generate_completion(model, tokenizer, problem["prompt"], args.max_new_tokens)
        tested = evaluate_completion(problem, completion, timeout=args.exec_timeout)
        record = {"task_id": problem["task_id"], "passed": tested["passed"],
                  "completion": completion, "error": tested["error"]}
        scanned.append(record)
        if len(selected) < args.edit_count and not tested["passed"]:
            # The source is a *successful canonical completion*, checked in the same container.
            reference_check = evaluate_completion(problem, problem["canonical_solution"], timeout=args.exec_timeout)
            if reference_check["passed"]:
                selected.append((problem, record))
                print(f"  {len(selected)}/{args.edit_count} failing cases: {problem['task_id']}", flush=True)
        elif len(selected) >= args.edit_count and len(holdout) < args.holdout_count:
            holdout.append((problem, record))
            print(f"  holdout {len(holdout)}/{args.holdout_count}: {problem['task_id']}", flush=True)
        if len(selected) >= args.edit_count and len(holdout) >= args.holdout_count:
            break
    if len(selected) != args.edit_count or len(holdout) != args.holdout_count:
        raise RuntimeError(f"Could not construct requested set: {len(selected)} failures, {len(holdout)} holdouts")

    progress = {
        "base_model": model_name, "source": DATA_URL, "max_new_tokens": args.max_new_tokens,
        "selected_failing_ids": [p["task_id"] for p, _ in selected],
        "holdout_ids": [p["task_id"] for p, _ in holdout],
        "candidate_scanned": len(scanned),
        "candidate_passed": sum(x["passed"] for x in scanned),
        "holdout_before_passes": sum(record["passed"] for _, record in holdout),
    }
    save_json(output / "progress.json", progress)

    print("Reading all 24 MLP projection keys/values on 20 paired examples...", flush=True)
    pairs = []
    for i, (problem, _record) in enumerate(selected, start=1):
        keys, _failed_values, logits = capture_layer_pairs(model, tokenizer, problem["prompt"])
        _success_keys, success_values, _ = capture_layer_pairs(
            model, tokenizer, problem["prompt"] + problem["canonical_solution"]
        )
        reference_tokens = tokenizer(problem["canonical_solution"], add_special_tokens=False)["input_ids"]
        target_token = reference_tokens[0]
        base_logprob = float(torch.log_softmax(logits, dim=-1)[target_token].item())
        pairs.append({"problem": problem, "keys": keys, "successful_values": success_values,
                      "target_token": target_token, "base_logprob": base_logprob})
        print(f"  captured {i}/{len(selected)}", flush=True)

    print("Causal patch scan over all 24 down_proj layers and all 20 pairs...", flush=True)
    causal = []
    for layer in range(len(model.model.layers)):
        changes = []
        for item in pairs:
            score = patched_first_token_logprob(
                model, tokenizer, item["problem"]["prompt"], layer,
                item["successful_values"][layer], item["target_token"]
            )
            changes.append(score - item["base_logprob"])
        mean_change = statistics.mean(changes)
        causal.append({"layer": layer, "mean_logprob_delta": mean_change,
                       "median_logprob_delta": statistics.median(changes),
                       "positive_cases": sum(x > 0 for x in changes), "cases": len(changes)})
        print(f"  layer {layer:02d}: mean Δlog p={mean_change:+.4f}", flush=True)
    selected_layer = max(causal, key=lambda item: item["mean_logprob_delta"])["layer"]
    progress.update({"selected_layer": selected_layer, "causal_scores": causal})
    save_json(output / "progress.json", progress)

    print(f"Applying closed-form rank-one edit at causal layer {selected_layer}...", flush=True)
    module = model.model.layers[selected_layer].mlp.down_proj
    before_stats = matrix_statistics(module.weight)
    left, right, math_report = derive_average_rank_one(
        module.weight,
        [item["keys"][selected_layer] for item in pairs],
        [item["successful_values"][selected_layer] for item in pairs],
        args.max_relative_change,
        args.alpha,
    )
    apply_weight_edit(model, selected_layer, "mlp.down_proj", left, right)
    after_stats = matrix_statistics(module.weight)
    save_file({"left": left.contiguous().cpu(), "right": right.contiguous().cpu()},
              str(output / "rome_factors.safetensors"))
    progress["edit"] = {"layer": selected_layer, "matrix": "mlp.down_proj",
                        "before": before_stats, "after": after_stats, **math_report}
    save_json(output / "progress.json", progress)

    print("Evaluating edited model on 20 failures and 20 untouched holdout tasks...", flush=True)
    after_selected = []
    after_holdout = []
    for group, destination in ((selected, after_selected), (holdout, after_holdout)):
        for problem, before in group:
            completion = generate_completion(model, tokenizer, problem["prompt"], args.max_new_tokens)
            checked = evaluate_completion(problem, completion, timeout=args.exec_timeout)
            destination.append({"task_id": problem["task_id"],
                                "before_passed": before["passed"],
                                "after_passed": checked["passed"],
                                "before_completion": before["completion"],
                                "after_completion": completion,
                                "after_error": checked["error"]})
            print(f"  {problem['task_id']}: {before['passed']} -> {checked['passed']}", flush=True)

    def scores(records):
        n = len(records)
        before = sum(r["before_passed"] for r in records)
        after = sum(r["after_passed"] for r in records)
        return {"n": n, "before_passed": before, "after_passed": after,
                "pass_at_1_before": before / n, "pass_at_1_after": after / n,
                "pass_at_1_delta": (after - before) / n,
                "percentage_point_delta": 100 * (after - before) / n}

    report = {
        **progress,
        "failure_conditioned_edit_set": scores(after_selected),
        "independent_holdout_20": scores(after_holdout),
        "methodology": {
            "k": "last-token input to each MLP down_proj, not the raw residual stream",
            "y": "last-token MLP output from a teacher-forced, sandbox-verified canonical solution",
            "causal_layer": "max mean log-probability increase for first canonical token under output activation patching",
            "rome_projection": "one rank-one update on mean of 20 key/value pairs, using Woodbury ridge covariance inverse",
            "caution": "Not full ROME; same 20 edit cases inform layer selection and edit. Holdout never informs selection.",
            "execution": "Docker restricted container, no host execution or network; one greedy generation per task",
        },
    }
    save_json(output / "rome20_report.json", report)
    save_json(output / "predictions.json", {"edited_cases": after_selected, "holdout_cases": after_holdout})
    print("Selected failure-set pass@1:", report["failure_conditioned_edit_set"], flush=True)
    print("INDEPENDENT holdout pass@1:", report["independent_holdout_20"], flush=True)
    print(f"Completed. Reports and reversible factors: {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="HumanEval 20-failure closed-form ROME-style direct weight edit")
    parser.add_argument("--edit-count", type=int, default=20)
    parser.add_argument("--holdout-count", type=int, default=20)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--exec-timeout", type=int, default=4)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--max-relative-change", type=float, default=0.01)
    parser.add_argument("--output", default="outputs/rome20")
    args = parser.parse_args()
    if not (1 <= args.edit_count <= 50 and 1 <= args.holdout_count <= 50):
        parser.error("edit and holdout counts must be between 1 and 50")
    if not 32 <= args.max_new_tokens <= 512:
        parser.error("max-new-tokens must be 32..512")
    if not 0 < args.alpha <= 1:
        parser.error("alpha must be in (0,1]")
    run(args)


if __name__ == "__main__":
    main()

