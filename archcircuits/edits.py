"""Phase C/D: closed-form, reversible weight-space interventions.

Three mathematically distinct candidate families are supported:

1. rank-one contrastive steering:  ΔW = α·d·uᵀ
   d is the gold-vs-wrong contrastive output direction at the causally
   selected layer; u = C⁻¹k̄/(k̄ᵀC⁻¹k̄) is the ridge-normalized mean key.

2. multi-key ridge steering (Woodbury, MEMIT-style closed form):
   ΔW = R (K + KC... ) solved via the regularized normal equations so that
   (W+ΔW)k_i ≈ W k_i + α d for every error-conditioned key k_i.

3. joint multi-category subspace edit: keys from several categories with
   per-category target directions, one bounded low-rank update.

All updates are capped by the repository norm limit (<= 1.5% relative
Frobenius norm per matrix), saved as small factor tensors, and exactly
reversible (W -= left @ right).  No gradients or optimizers anywhere.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import torch

from .benchmark import build_prompt
from .tracing import tokenize

MAX_REL_CHANGE = 0.015  # repository norm limit for bounded experiments


# ---------------------------------------------------------------------------
# activation capture at a chosen linear layer
# ---------------------------------------------------------------------------

@torch.inference_mode()
def capture_linear_at_positions(model, tokenizer, prompt: str, layer: int,
                                matrix: str, positions: list[int], answer: str | None = None) -> tuple[torch.Tensor, torch.Tensor]:
    """Return (keys, values) of the target linear layer at given positions.

    When `answer` is given, the run uses ID concatenation
    tok(prompt) ++ tok(answer) so positions align with generation exactly.
    """
    module = _resolve(model, layer, matrix)
    seen = {}

    def hook(_m, inputs, output):
        seen["k"] = inputs[0][0].detach().clone()
        seen["v"] = output[0].detach().clone()

    handle = module.register_forward_hook(hook)
    try:
        if answer is None:
            ids = tokenize(tokenizer, prompt)
        else:
            pre = tokenizer(prompt, add_special_tokens=False)["input_ids"]
            post = tokenizer(answer, add_special_tokens=False)["input_ids"]
            import torch as _t
            ids = {"input_ids": _t.tensor([pre + post], dtype=_t.long),
                   "attention_mask": _t.ones(1, len(pre) + len(post), dtype=_t.long)}
        model(**ids)
    finally:
        handle.remove()
    idx = torch.tensor(positions, dtype=torch.long)
    return seen["k"][idx, :].float(), seen["v"][idx, :].float()


def answer_positions(tokenizer, prompt: str, answer: str) -> tuple[list[int], int]:
    """Answer-token positions using ID concatenation (matches generation):
    input_ids = tok(prompt) ++ tok(answer), so the prefix length is exact and
    no BPE boundary merges can shift the answer positions."""
    prefix_len = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    n_answer = len(tokenizer(answer, add_special_tokens=False)["input_ids"])
    return list(range(prefix_len, prefix_len + n_answer)), prefix_len


def _resolve(model, layer_idx: int, matrix_name: str):
    component, projection = matrix_name.split(".")
    return getattr(getattr(model.model.layers[layer_idx], component), projection)


# ---------------------------------------------------------------------------
# contrastive direction and edit construction
# ---------------------------------------------------------------------------

def collect_contrast(model, tokenizer, pairs: list[dict], layer: int, matrix: str) -> dict:
    """pairs: [{prompt, gold, wrong}] -> activations at the first token where
    the gold and wrong answer continuations diverge (the 'commitment' token).

    Numeric answers tokenize digit-by-digit with a shared ' ' prefix, so the
    first *diverging* token is the meaningful contrast position; capturing at
    the bare space would give an identical activation for both continuations.
    """
    from .tracing import divergence_index

    v_gold, v_wrong, k_wrong, k_gold = [], [], [], []
    used = 0
    for p in pairs:
        prompt = p["prompt"]
        gold_ids = tokenizer(" " + p["gold"], add_special_tokens=False)["input_ids"]
        wrong_ids = tokenizer(" " + p["wrong"], add_special_tokens=False)["input_ids"]
        j = divergence_index(gold_ids, wrong_ids)
        if j >= min(len(gold_ids), len(wrong_ids)):
            continue  # answers do not diverge; skip this pair
        for ids, vlist, klist in ((gold_ids, v_gold, k_gold), (wrong_ids, v_wrong, k_wrong)):
            answer_text = tokenizer.decode(ids[: j + 1])
            prefix_len = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
            k, v = capture_linear_at_positions(
                model, tokenizer, prompt, layer, matrix,
                [prefix_len + j], answer=answer_text)
            vlist.append(v[0])
            klist.append(k[0])
        used += 1
    if used < max(1, len(pairs) // 2):
        raise RuntimeError(f"too few divergent pairs ({used}/{len(pairs)})")
    Vg = torch.stack(v_gold)
    Vw = torch.stack(v_wrong)
    Kg = torch.stack(k_gold)
    Kw = torch.stack(k_wrong)
    d = (Vg - Vw).mean(dim=0)
    return {
        "d": d,
        "keys_wrong": Kw,
        "keys_gold": Kg,
        "d_norm": float(d.norm().item()),
        "gold_mean_norm": float(Vg.norm(dim=1).mean().item()),
        "wrong_mean_norm": float(Vw.norm(dim=1).mean().item()),
        "cos_gold_wrong": float(torch.nn.functional.cosine_similarity(Vg, Vw, dim=1).mean().item()),
        "n_pairs": len(pairs),
    }


def ridge_inverse_keys(calibration_keys: torch.Tensor, queries: torch.Tensor,
                       ridge_fraction: float = 0.05) -> tuple[torch.Tensor, float]:
    """C⁻¹ Q with C = λI + KKᵀ/m via Woodbury (never builds the d×d matrix).

    calibration_keys: [d, m] (columns are keys); queries: [d, n].
    """
    k = calibration_keys.detach().float()
    q = queries.detach().float()
    ridge = max(float(k.square().mean().item()) * ridge_fraction, 1e-6)
    u = k / math.sqrt(k.shape[1])                       # [d, m]
    small = ridge * torch.eye(u.shape[1]) + u.T @ u      # [m, m]
    inverse = (q - u @ torch.linalg.solve(small, u.T @ q)) / ridge  # [d, n]
    if not torch.isfinite(inverse).all():
        raise RuntimeError("non-finite Woodbury inverse")
    return inverse, ridge


def rank_one_factors(weight: torch.Tensor, keys: torch.Tensor, d: torch.Tensor,
                     alpha: float) -> tuple[torch.Tensor, torch.Tensor, dict]:
    """ΔW = α d uᵀ with u = C⁻¹k̄/(k̄ᵀC⁻¹k̄); keys are error-conditioned rows [n, d]."""
    kbar = keys.mean(dim=0)                              # [d]
    inv_k, ridge = ridge_inverse_keys(keys.T.contiguous(), kbar.unsqueeze(1))  # [d, 1]
    u = inv_k[:, 0]                                      # C⁻¹k̄
    denom = float(torch.dot(kbar, u).item())
    if abs(denom) < 1e-10:
        raise ValueError("degenerate key geometry")
    right = u / denom                                    # [d]
    left = alpha * d                                     # [d_out]
    return left, right, {"ridge": ridge, "denominator": denom}


def multi_key_factors(weight: torch.Tensor, keys: torch.Tensor, d: torch.Tensor,
                      alpha: float, residual_fraction: float = 1.0
                      ) -> tuple[torch.Tensor, torch.Tensor, dict]:
    """Push every error-conditioned key's output toward W k_i + α d.

    Closed form (same regularized normal equations as tinycoder/rome_batch):
        ΔW = L R,  R = (C⁻¹K)ᵀ,  L = (I + KᵀC⁻¹K)⁻¹ (α d 1ᵀ)
    with keys as rows [n, d] here, transposed to the [d, n] convention inside.
    """
    K = keys.T.contiguous()                              # [d, n]
    n = K.shape[1]
    inv_keys, ridge = ridge_inverse_keys(K, K)           # [d, n] columns C⁻¹k_i
    gram = torch.eye(n) + K.T @ inv_keys                 # [n, n]
    residual = (alpha * residual_fraction * d).unsqueeze(1).expand(-1, n)  # [d_out, n]
    left = torch.linalg.solve(gram, residual.T).T.contiguous()   # [d_out, n]
    right = inv_keys.T.contiguous()                      # [n, d]
    return left, right, {"ridge": ridge, "rank": int(n),
                         "residual_fraction": residual_fraction}


def joint_factors(weight: torch.Tensor, key_groups: list[torch.Tensor],
                  dir_groups: list[torch.Tensor], alphas: list[float]
                  ) -> tuple[torch.Tensor, torch.Tensor, dict]:
    """Multi-category joint edit: per-key targets W k + α_cat · d_cat."""
    keys = torch.cat(key_groups, dim=0)                     # [n, d_in] rows
    targets = torch.cat([a * d for a, d in zip(alphas, dir_groups)], dim=0)  # [n, d_out]
    K = keys.T.contiguous()                                 # [d, n]
    n = K.shape[1]
    inv_keys, ridge = ridge_inverse_keys(K, K)              # [d, n]
    gram = torch.eye(n) + K.T @ inv_keys                    # [n, n]
    left = torch.linalg.solve(gram, targets).T.contiguous()  # [d_out, n]
    right = inv_keys.T.contiguous()                         # [n, d]
    return left, right, {"ridge": ridge, "rank": int(n),
                         "groups": [int(k.shape[0]) for k in key_groups]}


def cap_and_apply(model, layer: int, matrix: str, left: torch.Tensor, right: torch.Tensor,
                  max_relative_change: float = MAX_REL_CHANGE) -> dict:
    """Apply ΔW = left @ right in RAM after verifying the exact norm bound."""
    module = _resolve(model, layer, matrix)
    w = module.weight
    delta = (left @ right).to(dtype=w.dtype)
    proposal = float(delta.float().norm().item())
    wnorm = float(w.detach().float().norm().item())
    if proposal <= 0 or not math.isfinite(proposal):
        raise ValueError("degenerate edit")
    scale = min(1.0, max_relative_change * wnorm * 0.999 / proposal)
    delta = delta * scale
    with torch.no_grad():
        old_norm = float(w.detach().float().norm().item())
        w.add_(delta)
        observed = float(w.detach().float().norm().item())
    relative = abs(observed - old_norm) / old_norm  # norm change
    exact = float(delta.float().norm().item()) / wnorm
    if exact > max_relative_change + 1e-6:
        with torch.no_grad():
            w.sub_(delta)
        raise RuntimeError(f"edit exceeded cap ({exact:.4f}); reverted")
    if not torch.isfinite(w).all():
        with torch.no_grad():
            w.sub_(delta)
        raise RuntimeError("non-finite weights after edit; reverted")
    return {
        "proposed_delta_frob": proposal,
        "applied_scale": scale,
        "relative_delta_frob": round(exact, 6),
        "norm_before": round(old_norm, 4),
        "norm_after": round(observed, 4),
        "norm_change_ratio": round(relative, 6),
    }


# ---------------------------------------------------------------------------
# factor persistence
# ---------------------------------------------------------------------------

def save_factors(directory: str, layer: int, matrix: str, left: torch.Tensor,
                 right: torch.Tensor, meta: dict) -> dict:
    from safetensors.torch import save_file
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    save_file({"left": left.contiguous().cpu(), "right": right.contiguous().cpu()},
              str(out / "factors.safetensors"))
    full = {
        "method": "archcircuits_steer_v1",
        "base_model": "Qwen/Qwen2.5-Coder-0.5B",
        "layer_idx": layer,
        "matrix_name": matrix,
        "left_shape": list(left.shape),
        "right_shape": list(right.shape),
        **meta,
    }
    (out / "meta.json").write_text(json.dumps(full, indent=2) + "\n", encoding="utf-8")
    return full


def load_factor_set(model, directory: str, remove: bool = False) -> dict:
    """Apply (or revert) a saved factor set: W ±= left @ right."""
    from safetensors.torch import load_file
    out = Path(directory)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    if meta.get("base_model") != "Qwen/Qwen2.5-Coder-0.5B":
        raise ValueError("factor set is for a different base model")
    factors = load_file(str(out / "factors.safetensors"))
    left, right = factors["left"].float(), factors["right"].float()
    module = _resolve(model, meta["layer_idx"], meta["matrix_name"])
    w = module.weight
    if left.shape[0] != w.shape[0] or right.shape[1] != w.shape[1]:
        raise ValueError("factor shapes do not match the target matrix")
    delta = (left @ right).to(dtype=w.dtype)
    with torch.no_grad():
        w.add_(delta if not remove else -delta)
    if not torch.isfinite(w).all():
        raise RuntimeError("non-finite weights after factor application")
    return meta


def principal_angles(A: torch.Tensor, B: torch.Tensor) -> list[float]:
    """Principal angles (degrees) between column spaces of A and B."""
    import math as _m

    def ortho(M):
        q, _ = torch.linalg.qr(M.float())
        return q

    qa, qb = ortho(A), ortho(B)
    s = torch.linalg.svdvals(qa.T @ qb)
    return [round(float(_m.degrees(_m.acos(min(1.0, max(-1.0, float(v)))))), 2) for v in s]
