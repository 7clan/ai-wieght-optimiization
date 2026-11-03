"""Dataset validation and prompt/answer token preparation (no ML imports)."""

from __future__ import annotations

import json
from pathlib import Path

from . import SYSTEM_PROMPT


def read_examples(path: str | Path, *, require_answer: bool = True) -> list[dict]:
    """Read JSONL and reject missing, ambiguous, or unsafe-to-train-on rows."""
    examples = []
    seen_prompts = set()
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            prompt = item.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{path}:{line_number}: nonempty 'prompt' required")
            if prompt in seen_prompts:
                raise ValueError(f"{path}:{line_number}: duplicate prompt")
            seen_prompts.add(prompt)
            if require_answer and (not isinstance(item.get("answer"), str) or not item["answer"].strip()):
                raise ValueError(f"{path}:{line_number}: nonempty 'answer' required")
            examples.append(item)
    if not examples:
        raise ValueError(f"{path}: dataset is empty")
    return examples


def prompt_tokens(tokenizer, prompt: str) -> list[int]:
    """Use chat formatting where supported, plain completion otherwise."""
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            tokenize=True,
            add_generation_prompt=True,
        )
    return tokenizer(f"### Instruction:\n{prompt}\n### Response:\n", add_special_tokens=True)["input_ids"]


def supervised_tokens(tokenizer, example: dict, max_length: int) -> dict | None:
    """Only supervise answer tokens; skip overlength rows without silently clipping answers."""
    prefix = prompt_tokens(tokenizer, example["prompt"])
    if not tokenizer.eos_token:
        raise ValueError("Tokenizer must define eos_token")
    completion = tokenizer(example["answer"] + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
    if not completion or len(prefix) + len(completion) > max_length:
        return None
    return {
        "input_ids": prefix + completion,
        "attention_mask": [1] * (len(prefix) + len(completion)),
        "labels": [-100] * len(prefix) + completion,
    }


def check_no_overlap(train: list[dict], eval_examples: list[dict]) -> None:
    common = {x["prompt"].strip() for x in train} & {x["prompt"].strip() for x in eval_examples}
    if common:
        raise ValueError(f"Train/evaluation prompt overlap: {sorted(common)}")

