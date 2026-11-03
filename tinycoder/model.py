"""Shared inference path. A model download happens only when explicitly invoked."""

from __future__ import annotations

from .data import prompt_tokens


def load_inference(model_id: str, adapter: str | None = None, device: str = "auto",
                   edit: str | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
    model = model.to(device).eval()
    if edit:
        from .direct_edit import apply_saved_edit

        apply_saved_edit(model, model_id, edit)
    return model, tokenizer, device


def generate(model, tokenizer, prompt: str, max_new_tokens: int = 192, temperature: float = 0.0) -> str:
    import torch

    ids = prompt_tokens(tokenizer, prompt)
    model_device = next(model.parameters()).device
    input_ids = torch.tensor([ids], dtype=torch.long, device=model_device)
    kwargs = {"max_new_tokens": max_new_tokens, "do_sample": temperature > 0}
    if temperature > 0:
        kwargs["temperature"] = temperature
    if tokenizer.eos_token_id is not None:
        kwargs["pad_token_id"] = tokenizer.eos_token_id
    with torch.inference_mode():
        generated = model.generate(input_ids=input_ids, attention_mask=torch.ones_like(input_ids), **kwargs)
    return tokenizer.decode(generated[0, len(ids):], skip_special_tokens=True).strip()

