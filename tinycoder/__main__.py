"""Run with `python -m tinycoder --help`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import DEFAULT_MODEL, TINY_MODEL
from .data import check_no_overlap, read_examples, supervised_tokens
from .evaluation import static_check


def chat(args):
    from .model import generate, load_inference

    model, tokenizer, device = load_inference(args.model, args.adapter, args.device, args.edit, args.weight_edit)
    print(f"Model: {args.model} | device: {device} | edit: {args.weight_edit or args.edit or 'none'} | adapter: {args.adapter or 'none'}")
    print(generate(model, tokenizer, args.prompt, args.max_new_tokens, args.temperature))


def evaluate(args):
    from .model import generate, load_inference

    examples = read_examples(args.data, require_answer=False)
    for i, item in enumerate(examples, start=1):
        if not isinstance(item.get("expected_function"), str) or not item["expected_function"]:
            raise ValueError(f"Evaluation row {i} needs 'expected_function'")
    model, tokenizer, device = load_inference(args.model, args.adapter, args.device, args.edit, args.weight_edit)
    results = []
    for i, item in enumerate(examples, start=1):
        answer = generate(model, tokenizer, item["prompt"], args.max_new_tokens)
        checks = static_check(answer, item["expected_function"])
        results.append({"id": item.get("id", i), "prompt": item["prompt"], "answer": answer, **checks})
        print(f"[{i}/{len(examples)}] {item.get('id', i)}: static_pass={checks['static_pass']}")
    count = sum(x["static_pass"] for x in results)
    report = {
        "model": args.model,
        "adapter": args.adapter,
        "edit": args.edit,
        "weight_edit": args.weight_edit,
        "device": device,
        "evaluation_type": "AST syntax plus top-level function name; NOT a functional correctness test",
        "static_pass": count,
        "total": len(results),
        "results": results,
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Static checks: {count}/{len(results)}. Report: {output}")


def train(args):
    train_examples = read_examples(args.data)
    eval_examples = read_examples(args.eval_data, require_answer=False)
    check_no_overlap(train_examples, eval_examples)
    if args.model != DEFAULT_MODEL:
        raise ValueError("The training recipe currently supports only Qwen2.5-Coder-0.5B-Instruct; "
                         "the smaller StarCoder is available for inference experiments.")
    if args.max_length < 64 or args.epochs <= 0 or args.batch_size <= 0 or args.grad_accum <= 0:
        raise ValueError("max_length must be >=64; epochs/batch_size/grad_accum must be >0")
    print(f"Validated {len(train_examples)} training rows and {len(eval_examples)} disjoint held-out prompts")
    if args.dry_run:
        print("Dry run complete: no model downloaded, no weights changed.")
        return

    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from torch.utils.data import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    records = []
    for row in train_examples:
        encoded = supervised_tokens(tokenizer, row, args.max_length)
        if encoded is not None:
            records.append(encoded)
    skipped = len(train_examples) - len(records)
    if not records:
        raise ValueError("All rows exceed max_length; increase --max-length or shorten examples")
    if skipped:
        print(f"Skipped {skipped} long rows (no answer truncation)")

    class Rows(Dataset):
        def __len__(self):
            return len(records)

        def __getitem__(self, index):
            return records[index]

    def pad_batch(batch):
        width = max(len(row["input_ids"]) for row in batch)
        return {
            key: torch.tensor([
                row[key] + [(-100 if key == "labels" else (0 if key == "attention_mask" else tokenizer.pad_token_id))]
                * (width - len(row[key])) for row in batch
            ], dtype=torch.long)
            for key in ("input_ids", "attention_mask", "labels")
        }

    # Frozen base + small trainable matrices: genuine weight updates, with small adapters.
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.float32)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    ))
    model.print_trainable_parameters()
    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate,
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        remove_unused_columns=False,
        dataloader_pin_memory=False,
        use_cpu=args.cpu,
        seed=args.seed,
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=Rows(), data_collator=pad_batch)
    trainer.train()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(output))  # Save only the small LoRA adapter, not base weights.
    tokenizer.save_pretrained(str(output))
    (output / "run_metadata.json").write_text(json.dumps({
        "base_model": args.model,
        "training_examples": len(records),
        "skipped_examples": skipped,
        "held_out_examples": len(eval_examples),
        "epochs": args.epochs,
        "seed": args.seed,
        "max_length": args.max_length,
        "learning_rate": args.learning_rate,
        "note": "Toy demonstration dataset; improvement on unseen coding tasks is not established.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"LoRA adapter saved: {output}. Evaluate it against the held-out set next.")


def inspect(args):
    from .model import load_inference

    model, _, device = load_inference(args.model, args.adapter, args.device, args.edit, args.weight_edit)
    print(f"Model: {args.model} | device: {device}")
    printed = 0
    for name, param in model.named_parameters():
        if args.filter.lower() not in name.lower():
            continue
        data = param.detach().float()
        print(f"{name} | shape={tuple(data.shape)} | mean={data.mean().item():.6g} "
              f"| std={data.std(unbiased=False).item():.6g} | trainable={param.requires_grad}")
        printed += 1
        if printed >= args.limit:
            break
    if not printed:
        print("No matching parameter names. Use --filter '' to see base weights; "
              "LoRA weights are only present when --adapter is supplied.")


def direct_edit(args):
    from .direct_edit import create_edit
    from .model import load_inference

    model, tokenizer, device = load_inference(args.model, device=args.device)
    report = create_edit(model, tokenizer, args.model, args.prompt, args.target_token,
                         args.boost, args.output)
    print(f"Directly changed an output weight row on {device}; no training took place.")
    print(json.dumps(report, indent=2))


def weight_inspect(args):
    from .model import load_inference
    from .weight_space import matrix_statistics, target_linear

    model, _, device = load_inference(args.model, device=args.device)
    module = target_linear(model, args.layer, args.matrix)
    report = matrix_statistics(module.weight)
    print(json.dumps({"model": args.model, "device": device, "layer": args.layer,
                      "matrix": args.matrix, **report}, indent=2))


def weight_edit(args):
    from .model import load_inference
    from .weight_space import create_weight_edit

    calibration = read_examples(args.calibration, require_answer=False)
    model, tokenizer, device = load_inference(args.model, device=args.device)
    report = create_weight_edit(
        model, tokenizer, args.model,
        layer_idx=args.layer, matrix_name=args.matrix, method=args.method,
        prompt=args.prompt, reference_prompt=args.reference_prompt,
        calibration_prompts=[x["prompt"] for x in calibration],
        alpha=args.alpha, max_relative_change=args.max_relative_change,
        output_directory=args.output,
    )
    print(f"Edited actual internal tensor on {device}. No optimizer or training was used.")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description="TinyCoder: small model, measurable training experiments")
    commands = parser.add_subparsers(dest="command", required=True)

    def model_options(command):
        command.add_argument("--model", default=DEFAULT_MODEL,
                             help=f"Default: {DEFAULT_MODEL}; tiny comparison: {TINY_MODEL}")
        command.add_argument("--adapter", help="Path to a trained LoRA adapter")
        command.add_argument("--edit", help="Path to a saved direct weight edit")
        command.add_argument("--weight-edit", help="Path to saved internal rank-one/nullspace weight edit")
        command.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")

    p = commands.add_parser("chat", help="Generate a coding answer locally")
    p.add_argument("prompt", help="Your coding instruction or, for Tiny StarCoder, a completion prefix")
    model_options(p)
    p.add_argument("--max-new-tokens", type=int, default=192)
    p.add_argument("--temperature", type=float, default=0.0)
    p.set_defaults(func=chat)

    p = commands.add_parser("train", help="Fine-tune Qwen with LoRA on your own examples")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--data", default="data/train.jsonl")
    p.add_argument("--eval-data", default="data/eval.jsonl")
    p.add_argument("--output", default="checkpoints/session-001")
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=0.0002)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cpu", action="store_true", help="Force CPU (very slow; GPU recommended)")
    p.add_argument("--dry-run", action="store_true", help="Validate data without downloading the model")
    p.set_defaults(func=train)

    p = commands.add_parser("eval", help="Save generated answers and safe, basic static checks")
    model_options(p)
    p.add_argument("--data", default="data/eval.jsonl")
    p.add_argument("--report", default="outputs/eval.json")
    p.add_argument("--max-new-tokens", type=int, default=192)
    p.set_defaults(func=evaluate)

    p = commands.add_parser("inspect", help="Read weight names, shapes and statistics")
    model_options(p)
    p.add_argument("--filter", default="lora_", help="Parameter name substring (default: LoRA only)")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=inspect)

    p = commands.add_parser("edit", help="Directly change one output weight row, no training")
    p.add_argument("prompt", help="Prompt whose next-token distribution should be changed")
    p.add_argument("--target-token", required=True, help="One tokenizer token to make more likely")
    p.add_argument("--boost", type=float, default=2.0, help="Requested next-token logit increase, max 5")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    p.add_argument("--output", default="edits/direct-001")
    p.set_defaults(func=direct_edit)

    p = commands.add_parser("weight-inspect", help="Read stats of a specific internal weight matrix")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    p.add_argument("--layer", type=int, default=12)
    p.add_argument("--matrix", default="mlp.down_proj")
    p.set_defaults(func=weight_inspect)

    p = commands.add_parser("weight-edit", help="Closed-form update to an internal matrix, no training")
    p.add_argument("prompt", help="Target prompt to modify internally")
    p.add_argument("--reference-prompt", help="Prompt whose activation provides the desired value (rank-one)")
    p.add_argument("--method", choices=["rank-one", "nullspace"], default="rank-one")
    p.add_argument("--layer", type=int, default=12)
    p.add_argument("--matrix", default="mlp.down_proj")
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--max-relative-change", type=float, default=0.002)
    p.add_argument("--calibration", default="data/calibration.jsonl")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    p.add_argument("--output", default="edits/internal-001")
    p.set_defaults(func=weight_edit)

    args = parser.parse_args()
    if args.command == "chat" and (args.max_new_tokens <= 0 or args.temperature < 0):
        parser.error("max-new-tokens must be positive and temperature nonnegative")
    args.func(args)


if __name__ == "__main__":
    main()

