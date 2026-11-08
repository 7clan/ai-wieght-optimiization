"""Narrow JSON protocol between the frozen Qwen model and the controller.

No model is downloaded or invoked on import. The caller explicitly supplies
the inference function; Qwen runs only if the caller opts in.
"""

from __future__ import annotations

import json
from typing import Callable

from .controller import ControllerError, ModelContext, Proposal


class QwenJSONAdapter:
    def __init__(self, generate_text: Callable[[str], str]) -> None:
        self.generate_text = generate_text

    def propose(self, context: ModelContext) -> Proposal:
        public_checks = "\n".join(f"- {c}" for c in context.task.public_acceptance)
        feedback = "\n".join(context.public_feedback[-2:])[:2400]
        docs = "\n".join(
            f"Source: {x.source_url}\n{x.excerpt[:800]}" for x in context.documentation[-2:]
        )
        prompt = (
            "You are a small coding model operating within a bounded testing loop.\n"
            "Produce one coherent implementation, not a tutorial.\n"
            'Reply with ONLY a JSON object: {"files":{"relative/path":"content"},'
            '"hypothesis":"why it should work","uncertain":false,'
            '"research_queries":[]}.\n'
            "Use only relative paths. Do not fabricate tool outcomes.\n"
            f"TASK: {context.task.description[:1600]}\n"
            f"PUBLIC ACCEPTANCE:\n{public_checks[:1600]}\n"
            f"CURRENT STRATEGY: {context.strategy[:600]}\n"
            f"PREVIOUS PUBLIC ERRORS:\n{feedback}\n"
            f"DOCUMENTATION:\n{docs}\n"
        )
        raw = self.generate_text(prompt).strip()
        if raw.startswith("```json"):
            raw = raw[7:]
            if raw.endswith("```"):
                raw = raw[:-3]
        try:
            obj = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError) as exc:
            raise ControllerError("Qwen response is not one valid JSON object") from exc
        if not isinstance(obj, dict):
            raise ControllerError("Qwen response must be a JSON object")
        files = obj.get("files")
        if not isinstance(files, dict):
            raise ControllerError("Qwen response needs a files object")
        queries = obj.get("research_queries", [])
        if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
            raise ControllerError("research_queries must be strings")
        return Proposal(
            files=files,
            hypothesis=str(obj.get("hypothesis", "unexplained change"))[:400],
            uncertain=obj.get("uncertain", False) is True,
            research_queries=tuple(queries[:3]),
        )


def load_local_qwen(model_id: str = "Qwen/Qwen2.5-Coder-0.5B-Instruct") -> QwenJSONAdapter:
    """Explicitly load one model; model cache/download requirements are caller's.

    The default is the frozen 0.5B Instruct checkpoint. No adapters or edits.
    """
    from tinycoder.model import generate, load_inference

    model, tokenizer, _ = load_inference(model_id, device="cpu")
    return QwenJSONAdapter(lambda prompt: generate(
        model, tokenizer, prompt, max_new_tokens=1024, temperature=0,
    ))
