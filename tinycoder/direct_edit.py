"""Deterministic, gradient-free editing of one output-embedding weight row.

This is an educational one-token intervention, NOT ROME/MEMIT and not a way
to transfer broad reasoning ability. The original model remains unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import prompt_tokens


def apply_saved_edit(model, model_id: str, directory: str):
    """Apply a stored additive row delta, with strict base-model and shape checks."""
    import torch
    from safetensors.torch import load_file

    folder = Path(directory)
    metadata = json.loads((folder / "edit.json").read_text(encoding="utf-8"))
    if metadata["base_model"] != model_id or metadata["method"] != "output_row_delta_v1":
        raise ValueError("Edit does not belong to this base model/method")
    delta = load_file(str(folder / "edit.safetensors"))["delta"]
    output = model.get_output_embeddings().weight
    token_id = metadata["token_id"]
    if not (0 <= token_id < output.shape[0]) or delta.shape != output[token_id].shape:
        raise ValueError("Edit token or weight dimensions do not match model")
    with torch.no_grad():
        output[token_id].add_(delta.to(device=output.device, dtype=output.dtype))
    return metadata


def create_edit(model, tokenizer, model_id: str, prompt: str, target_token: str,
                requested_boost: float, output_directory: str) -> dict:
    """Change one actual tensor row to raise one chosen next-token logit.

    For last hidden vector h, a row delta (boost / ||h||²) * h targets a logit
    increase of `boost`, provided h remains fixed. Tied token embeddings may
    change h too, so we re-run inference and report the observed difference.
    """
    import torch
    from safetensors.torch import save_file

    if not (0 < requested_boost <= 5.0):
        raise ValueError("--boost must be >0 and <=5.0 logits to limit collateral damage")
    token_ids = tokenizer(target_token, add_special_tokens=False)["input_ids"]
    if len(token_ids) != 1:
        raise ValueError(f"Target {target_token!r} splits into {len(token_ids)} tokens; "
                         "choose exactly one tokenizer token")
    target_id = token_ids[0]
    output_weights = model.get_output_embeddings().weight
    tokens = torch.tensor([prompt_tokens(tokenizer, prompt)], dtype=torch.long,
                          device=output_weights.device)
    with torch.inference_mode():
        before = model(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                       output_hidden_states=True)
        hidden = before.hidden_states[-1][0, -1].detach().float()
        score_before = before.logits[0, -1, target_id].item()
        top_before = before.logits[0, -1].argmax().item()
        rank_before = int((before.logits[0, -1] > score_before).sum().item()) + 1
        highest_before = before.logits[0, -1, top_before].item()
        denom = torch.dot(hidden, hidden).item()
        if denom < 1e-10:
            raise ValueError("Hidden vector nearly zero; cannot safely edit")
        delta = requested_boost * hidden / denom
        output_weights[target_id].add_(delta.to(output_weights.dtype))
        after = model(input_ids=tokens, attention_mask=torch.ones_like(tokens))
        score_after = after.logits[0, -1, target_id].item()
        top_after = after.logits[0, -1].argmax().item()
        rank_after = int((after.logits[0, -1] > score_after).sum().item()) + 1
    path = Path(output_directory)
    path.mkdir(parents=True, exist_ok=True)
    save_file({"delta": delta.cpu().contiguous()}, str(path / "edit.safetensors"))
    report = {
        "method": "output_row_delta_v1",
        "base_model": model_id,
        "prompt": prompt,
        "target_token": target_token,
        "token_id": target_id,
        "requested_logit_boost": requested_boost,
        "actual_logit_change": round(score_after - score_before, 6),
        "target_logit_before": round(score_before, 6),
        "target_logit_after": round(score_after, 6),
        "highest_logit_before": round(highest_before, 6),
        "target_rank_before": rank_before,
        "target_rank_after": rank_after,
        "top_token_before": tokenizer.decode([top_before]),
        "top_token_after": tokenizer.decode([top_after]),
        "delta_l2_norm": round(delta.norm().item(), 9),
        "note": "Direct one-token weight edit, no backpropagation, optimizer, LoRA or training.",
    }
    (path / "edit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report

