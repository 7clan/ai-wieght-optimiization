"""Closed-form edits to an existing transformer's internal linear layers.

No gradients, training, optimizer, or extra trainable adapter is used here.
This is a *research demonstration*, not a faithful implementation of ROME
or MEMIT and not an established way to improve general coding ability.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import prompt_tokens


ALLOWED_MATRICES = frozenset({
    "self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj",
    "mlp.gate_proj", "mlp.up_proj", "mlp.down_proj",
})


def target_linear(model, layer_idx: int, matrix_name: str):
    """Resolve an explicitly allowlisted weight from a Qwen-like decoder."""
    import torch

    layers = model.model.layers
    if not 0 <= layer_idx < len(layers):
        raise ValueError(f"layer index {layer_idx} is outside 0..{len(layers) - 1}")
    if matrix_name not in ALLOWED_MATRICES:
        raise ValueError(f"Unknown matrix {matrix_name!r}; expected one of {sorted(ALLOWED_MATRICES)}")
    component, projection = matrix_name.split(".")
    module = getattr(getattr(layers[layer_idx], component), projection)
    if not isinstance(module, torch.nn.Linear):
        raise ValueError(f"{matrix_name} is not a standard linear matrix")
    return module


def get_layer_weights(model, layer_idx: int, matrix_name: str):
    """Return an immutable-by-convention tensor snapshot plus summary metrics."""
    module = target_linear(model, layer_idx, matrix_name)
    return module.weight.detach().float().cpu().clone(), matrix_statistics(module.weight)


def matrix_statistics(matrix, *, svd_sample: int = 128) -> dict:
    """Norms and approximate sampled singular values, never full-matrix SVD."""
    import torch

    with torch.no_grad():
        values = matrix.detach().float().cpu()
        sample = values[:min(svd_sample, values.shape[0]), :min(svd_sample, values.shape[1])]
        singular = torch.linalg.svdvals(sample).cpu()
        return {
            "shape": list(values.shape),
            "finite": bool(torch.isfinite(values).all().item()),
            "frob_norm": float(torch.linalg.vector_norm(values).item()),
            "mean": float(values.mean().item()),
            "std": float(values.std(unbiased=False).item()),
            "sampled_top_singular_values": [round(float(x), 6) for x in singular[:3]],
            "svd_note": f"Singular values from top-left {sample.shape[0]}x{sample.shape[1]} submatrix, NOT full matrix",
        }


def capture_io(model, tokenizer, prompt: str, layer_idx: int, matrix_name: str):
    """Read input key and output value at the last token for one linear layer."""
    import torch

    module = target_linear(model, layer_idx, matrix_name)
    observed = {}

    def hook(_module, input_values, output_values):
        observed["key"] = input_values[0][0, -1].detach().float().cpu().clone()
        observed["value"] = output_values[0, -1].detach().float().cpu().clone()

    handle = module.register_forward_hook(hook)
    try:
        token_ids = prompt_tokens(tokenizer, prompt)
        tensor = torch.tensor([token_ids], dtype=torch.long, device=module.weight.device)
        with torch.inference_mode():
            model(input_ids=tensor, attention_mask=torch.ones_like(tensor))
    finally:
        handle.remove()
    if "key" not in observed:
        raise RuntimeError("Failed to capture target projection input/output")
    return observed["key"], observed["value"]


def rank_one_factors(weight, key, desired_value, covariance_diagonal, alpha: float):
    """Solve ΔW = α (y-Wk) (C^-1 k)^T / (k^T C^-1 k), using diagonal C."""
    import torch

    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    w, k, y, c = (x.detach().float().cpu() for x in (weight, key, desired_value, covariance_diagonal))
    if w.ndim != 2 or k.shape != (w.shape[1],) or y.shape != (w.shape[0],) or c.shape != k.shape:
        raise ValueError("Incompatible matrix, key, target, or diagonal covariance shapes")
    if not bool(torch.isfinite(c).all()) or not bool((c > 0).all()):
        raise ValueError("Covariance diagonal must be positive and finite")
    direction = k / c
    denominator = torch.dot(k, direction)
    if denominator.item() <= 1e-10:
        raise ValueError("Key is too small to edit reliably")
    return alpha * (y - w @ k), direction / denominator


def nullspace_factors(weight, vector, strength: float, axis: str = "input"):
    """Rank-one dampening: W(I-s vvᵀ) or (I-s vvᵀ)W for unit v."""
    import torch

    if not 0 < strength <= 1:
        raise ValueError("strength must be in (0, 1]")
    w, v = weight.detach().float().cpu(), vector.detach().float().cpu()
    expected_length = w.shape[1] if axis == "input" else w.shape[0]
    if axis not in ("input", "output") or v.shape != (expected_length,):
        raise ValueError("Invalid axis or vector shape")
    norm = torch.linalg.vector_norm(v)
    if norm.item() <= 1e-10:
        raise ValueError("Cannot dampen a zero direction")
    unit = v / norm
    if axis == "input":
        return -strength * (w @ unit), unit
    return -strength * unit, w.T @ unit


def cap_factors(weight, left, right, max_relative_change: float):
    """Bound ||ΔW||_F / ||W||_F without materializing a dense edit."""
    import torch

    if not 0 < max_relative_change <= 0.05:
        raise ValueError("max-relative-change must be in (0, 0.05]")
    limit = float(torch.linalg.vector_norm(weight.detach().float()).item()) * max_relative_change
    proposed = float((torch.linalg.vector_norm(left) * torch.linalg.vector_norm(right)).item())
    if not proposed or not torch.isfinite(torch.tensor(proposed)):
        raise ValueError("Degenerate or non-finite edit")
    scale = min(1.0, limit / proposed)
    return left * scale, right, proposed, scale


def apply_weight_edit(model, layer_idx: int, matrix_name: str, left, right):
    """Actually overwrite selected model weights in RAM, after shape and finiteness checks."""
    import torch

    module = target_linear(model, layer_idx, matrix_name)
    weights = module.weight
    if left.shape != (weights.shape[0],) or right.shape != (weights.shape[1],):
        raise ValueError("Rank-one update factors do not match weight dimensions")
    if not bool(torch.isfinite(left).all()) or not bool(torch.isfinite(right).all()):
        raise ValueError("Non-finite update factors")
    with torch.no_grad():
        weights.add_(torch.outer(left, right).to(device=weights.device, dtype=weights.dtype))
    if not bool(torch.isfinite(weights).all()):
        raise RuntimeError("Non-finite edited weights; discard the model instance")


def apply_saved_weight_edit(model, model_id: str, directory: str) -> dict:
    from safetensors.torch import load_file

    folder = Path(directory)
    metadata = json.loads((folder / "weight_edit.json").read_text(encoding="utf-8"))
    if metadata.get("base_model") != model_id or metadata.get("method") != "internal_rank_one_v1":
        raise ValueError("Saved edit is not compatible with the requested base model")
    factors = load_file(str(folder / "factors.safetensors"))
    apply_weight_edit(model, metadata["layer_idx"], metadata["matrix_name"], factors["left"], factors["right"])
    return metadata


def create_weight_edit(model, tokenizer, model_id: str, *, layer_idx: int,
                       matrix_name: str, method: str, prompt: str,
                       reference_prompt: str | None, calibration_prompts: list[str],
                       alpha: float, max_relative_change: float, output_directory: str) -> dict:
    """Make a closed-form edit and write a compact, reversible factorization."""
    import torch
    from safetensors.torch import save_file

    if method not in ("rank-one", "nullspace"):
        raise ValueError("method must be rank-one or nullspace")
    if method == "rank-one" and not reference_prompt:
        raise ValueError("rank-one needs a reference prompt from which to read a target activation")
    folder = Path(output_directory)
    if (folder / "weight_edit.json").exists() or (folder / "factors.safetensors").exists():
        raise FileExistsError(f"{folder} already contains an edit; choose a fresh output directory")
    module = target_linear(model, layer_idx, matrix_name)
    original = matrix_statistics(module.weight)
    key, original_value = capture_io(model, tokenizer, prompt, layer_idx, matrix_name)
    if method == "rank-one":
        _, desired_value = capture_io(model, tokenizer, reference_prompt, layer_idx, matrix_name)
        if not calibration_prompts:
            raise ValueError("At least one calibration prompt is required")
        examples = [capture_io(model, tokenizer, p, layer_idx, matrix_name)[0]
                    for p in calibration_prompts]
        covariance = torch.stack(examples).square().mean(dim=0)
        ridge = max(float(covariance.mean().item()) * 0.01, 1e-6)
        covariance += ridge
        left, right = rank_one_factors(module.weight, key, desired_value, covariance, alpha)
    else:
        desired_value = None
        left, right = nullspace_factors(module.weight, key, alpha, axis="input")
    left, right, proposed_norm, scale = cap_factors(module.weight, left, right, max_relative_change)
    apply_weight_edit(model, layer_idx, matrix_name, left, right)
    edited = matrix_statistics(module.weight)
    if method == "rank-one":
        actual_output = (module.weight.detach().float().cpu() @ key)
        original_distance = float(torch.linalg.vector_norm(original_value - desired_value).item())
        edited_distance = float(torch.linalg.vector_norm(actual_output - desired_value).item())
    else:
        original_distance = edited_distance = None
    folder.mkdir(parents=True, exist_ok=True)
    save_file({"left": left.contiguous(), "right": right.contiguous()}, str(folder / "factors.safetensors"))
    result = {
        "method": "internal_rank_one_v1",
        "operation": method,
        "base_model": model_id,
        "layer_idx": layer_idx,
        "matrix_name": matrix_name,
        "prompt": prompt,
        "reference_prompt": reference_prompt,
        "alpha": alpha,
        "max_relative_change": max_relative_change,
        "proposed_delta_frob_norm": proposed_norm,
        "cap_scale_applied": scale,
        "actual_delta_relative_norm": float((torch.linalg.vector_norm(left) * torch.linalg.vector_norm(right)).item()) / original["frob_norm"],
        "before": original,
        "after": edited,
        "reference_activation_distance_before": original_distance,
        "reference_activation_distance_after": edited_distance,
        "note": "Direct internal matrix edit without gradient training; behavioral improvement not established",
    }
    (folder / "weight_edit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

