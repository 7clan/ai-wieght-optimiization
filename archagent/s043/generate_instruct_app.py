"""Generate a genuinely model-authored offline app with Qwen Instruct.

This driver never executes the generated HTML/JavaScript. The output is
UNTRUSTED and must be behavior-tested inside an isolated, network-disabled
container before being described as a working application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time


MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
SYSTEM = (
    "You are a careful web developer. Output only the complete HTML source. "
    "No Markdown fences, explanations, placeholders, or external dependencies."
)
TASK = """Create ONE standalone index.html app named FocusBoard for a person managing daily tasks.
The app must really work completely offline (no fetch, CDN, imports, frameworks, or remote resources).
Requirements:
1. An accessible form with a text input and Add Task button that inserts nonempty tasks.
2. A visible task list that shows all saved tasks.
3. A checkbox/button to mark each task completed and undo completion.
4. A Delete button for each task.
5. All, Active, and Completed filters that genuinely change the visible list.
6. Persist changes in localStorage and restore saved tasks after reload.
7. Show remaining active task count; provide an empty-state message.
8. Responsive professional CSS embedded in a style tag.
Use simple vanilla JavaScript (no TypeScript). Attach event listeners after the elements exist.
Keep implementation compact. End with </html>. Return only source, starting with <!DOCTYPE html>."""

REPAIR_FEEDBACK = """PUBLIC FEEDBACK FROM THE PREVIOUS ATTEMPT (not secret tests):
- The Add Task form submitted without preventDefault(), causing navigation.
- Appending bare task strings to innerHTML did not create actual task-list items.
- There were no completion or delete controls for individual tasks.
- Filters modified HTML strings instead of filtering task objects.
- Saving was never called after mutations; NodeList.map is invalid.
Generate a NEW, complete HTML file from scratch. Do not reuse the previous failed code.
Use a JavaScript array of task objects with id, text and completed boolean.
Every action must update that array, save JSON to localStorage, and render the list.
Create one <li> per task with a checkbox, label and Delete button.
Implement separate All, Active and Completed buttons and filter the task array.
The form submit handler MUST call preventDefault().
Please prioritize correct JavaScript over decorative CSS. Keep it short and executable."""


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_html(raw: str) -> tuple[str, dict[str, bool]]:
    """Deterministic extraction; no manual changes or generated-code repair."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:html)?\s*\n", "", text, count=1, flags=re.I)
        text = re.sub(r"\n```\s*$", "", text, count=1)
    start = re.search(r"<!doctype\s+html\s*>", text, re.I)
    end = list(re.finditer(r"</html\s*>", text, re.I))
    if start is not None and end:
        text = text[start.start():end[-1].end()]
    checks = {
        "doctype": bool(re.search(r"^<!doctype\s+html\s*>", text, re.I)),
        "closed_html": bool(re.search(r"</html\s*>\s*$", text, re.I)),
        "contains_style": "<style" in text.lower(),
        "contains_script": "<script" in text.lower(),
        "no_external_imports": not bool(re.search(r"\b(?:fetch\s*\(|import\s+.*from\s+|https?://)", text, re.I)),
    }
    return text, checks


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default=MODEL_ID)
    p.add_argument("--output-dir", type=Path, default=Path("experiments/z043-instruct-app"))
    p.add_argument("--max-new-tokens", type=int, default=2300)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--repair", action="store_true", help="Regenerate once from public failure feedback")
    args = p.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(args.threads)
    torch.manual_seed(20261111)
    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32).eval()
    task = TASK + ("\n\n" + REPAIR_FEEDBACK if args.repair else "")
    prompt = tokenizer.apply_chat_template(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    num_new = int(output.shape[1] - inputs["input_ids"].shape[1])
    raw = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    html, checks = extract_html(raw)
    target = args.output_dir
    target.mkdir(parents=True, exist_ok=True)
    (target / "raw_completion.txt").write_text(raw, encoding="utf-8")
    (target / "index.html").write_text(html, encoding="utf-8")
    report = {
        "attribution": "QWEN_2_5_CODER_0_5B_INSTRUCT_RAW_UNEDITED",
        "model": args.model,
        "prompt": {"system": SYSTEM, "task": task},
        "repair_from_public_feedback": args.repair,
        "prompt_sha256": sha256(prompt),
        "raw_sha256": sha256(raw),
        "extracted_sha256": sha256(html),
        "extraction": "doctype through final html closing tag, with optional fenced-code removal",
        "structural_checks": checks,
        "generation_tokens": num_new,
        "max_new_tokens": args.max_new_tokens,
        "wall_seconds_including_load": round(time.monotonic() - started, 2),
        "behavior_tested": False,
        "safe_to_run_unsandboxed": False,
        "note": "Output requires independent restricted-container behavioral validation.",
    }
    (target / "generation_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "generation_tokens": num_new, "seconds": report["wall_seconds_including_load"], "output_dir": str(target)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
