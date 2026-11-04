"""Out-of-sample confirmation and reversible Layer-8 SVD/MEMIT fusion.

The 144..163 block is evaluated for the preselected 10% edit *before* the
hybrid is constructed or scored. The 94..143 benchmark was already consumed
in Session 007. No derivatives, losses, or optimizers are involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

SOURCE_COMMIT = "b48673a26e7ef6a6220aca331dfc8c0024944aa8"
PREVIOUS_START, PREVIOUS_COUNT = 94, 50
FINAL_START, FINAL_COUNT = 144, 20
COMPARISON_COUNT = 70


def contiguous_tasks(problems, start: int, count: int):
    expected = [f"HumanEval/{i}" for i in range(start, start + count)]
    selected = problems[start:start + count]
    if [item["task_id"] for item in selected] != expected or len(problems) != 164:
        raise ValueError("Official HumanEval ordering or count changed")
    return selected


def tensor_factors(path: Path, keys: tuple[str, str]):
    import torch
    from safetensors.torch import load_file

    contents = load_file(str(path), device="cpu")
    if not all(key in contents for key in keys):
        raise ValueError(f"Missing expected factor keys in {path.name}: {keys}")
    left, right = (contents[key].detach().float().contiguous().clone() for key in keys)
    if (left.ndim != 2 or right.ndim != 2 or left.shape[1] != right.shape[0]
            or not torch.isfinite(left).all() or not torch.isfinite(right).all()):
        raise ValueError("Factors have incompatible dimensions or non-finite values")
    return left, right


def apply_reversible(module, left, right, *, expected_change: float, tolerance=0.000015):
    """Apply only a previously archived, shape-checked low-rank delta in RAM."""
    import torch

    original = module.weight.detach().clone()
    # Accept archived rank-one vector pairs as well as rank-two MEMIT factors.
    if left.ndim == 1 and right.ndim == 1:
        left, right = left[:, None], right[None, :]
    elif left.ndim != 2 or right.ndim != 2:
        raise ValueError("Expected paired rank-one vectors or rank-two factors")
    delta = left @ right
    if delta.shape != original.shape or not torch.isfinite(delta).all():
        raise ValueError("Factor product does not match the selected matrix")
    with torch.no_grad():
        module.weight.add_(delta.to(dtype=original.dtype, device=original.device))
    observed = float((torch.linalg.vector_norm((module.weight - original).float())
                      / torch.linalg.vector_norm(original.float())).item())
    if not torch.isfinite(module.weight).all() or abs(observed - expected_change) > tolerance:
        with torch.no_grad():
            module.weight.copy_(original)
        raise ValueError(f"Unexpected weight change; restored checkpoint: {observed:.8f}")
    return observed


def summarize(problems, base_completions, base_tests, edited_completions, edited_tests):
    from .branch_experiments import syntax_counts
    from .rome_batch import evaluate_records

    records = evaluate_records(problems, base_completions, edited_completions,
                               base_tests, edited_tests)
    count = len(records)
    ids = [item["task_id"] for item in records]
    if count not in (FINAL_COUNT, COMPARISON_COUNT) or len(set(ids)) != count:
        raise ValueError("Incomplete/duplicated evaluation records")
    before_ids = [item["task_id"] for item in records if item["before_passed"]]
    after_ids = [item["task_id"] for item in records if item["after_passed"]]
    syntax_before = syntax_counts(problems, base_completions)
    syntax_after = syntax_counts(problems, edited_completions)
    result = {
        "n": count,
        "before_passes": len(before_ids), "after_passes": len(after_ids),
        "pass_at_1_before": len(before_ids) / count,
        "pass_at_1_after": len(after_ids) / count,
        "percentage_point_delta": (len(after_ids) - len(before_ids)) * 100 / count,
        "passed_ids_before": before_ids, "passed_ids_after": after_ids,
        "failed_ids_before": [x for x in ids if x not in before_ids],
        "failed_ids_after": [x for x in ids if x not in after_ids],
        "newly_passed_ids": [x for x in after_ids if x not in before_ids],
        "regressed_ids": [x for x in before_ids if x not in after_ids],
        "changed_completions": sum(a != b for a, b in zip(base_completions, edited_completions, strict=True)),
        "syntax_before": syntax_before,
        "syntax_after": syntax_after,
        "syntax_validity_before": syntax_before["valid"] / count,
        "syntax_validity_after": syntax_after["valid"] / count,
        "execution_measure": "Docker-isolated official HumanEval test assertions; failed cases include runtime/semantic failures",
        "syntax_measure": "Python ast.parse(prompt + completion); syntax validity does not imply runtime correctness",
    }
    return result, records


def base_model_and_tokenizer():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from .rome20 import BASE_MODEL

    print(f"Loading {BASE_MODEL} on 4-thread CPU, greedy decoding", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.float32).eval().to("cpu")
    return model, tokenizer, torch.device("cpu")


def save_report(destination: Path, report, predictions):
    from .rome20 import save_json

    destination.mkdir(parents=True, exist_ok=True)
    save_json(destination / "report.json", report)
    save_json(destination / "predictions.json", predictions)


def fingerprint(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_reference_isolation(source_progress: Path):
    from .rome20 import BASE_MODEL, DATA_URL

    prior = json.loads(source_progress.read_text(encoding="utf-8"))
    if prior.get("base_model") != BASE_MODEL or prior.get("source") != DATA_URL:
        raise ValueError("Edited reference set provenance changed")
    if any(int(task.split("/")[-1]) >= PREVIOUS_START for task in prior["selected_failing_ids"]):
        raise ValueError("Editing references overlap either subsequent benchmark")


def validate_final(args):
    """One-time confirmation on 144..163, before evaluating the hybrid."""
    import torch
    from .branch_experiments import syntax_counts
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
    from .rome_batch import generate_batches, parallel_execution
    from .weight_space import target_linear

    problems = contiguous_tasks(fetch_problems(), FINAL_START, FINAL_COUNT)
    model, tokenizer, device = base_model_and_tokenizer()
    destination = Path(args.output_dir)
    print("20 untouched tasks: baseline (no edit)", flush=True)
    baseline = generate_batches(model, tokenizer, problems, device=device,
                                batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    before_tests = parallel_execution(problems, baseline, workers=args.workers, timeout=args.exec_timeout)
    save_json(destination / "progress.json", {"phase": "fresh_baseline_finished", "ids": [p["task_id"] for p in problems]})

    down = target_linear(model, 8, "mlp.down_proj")
    original = down.weight.detach().clone()
    factors10 = tensor_factors(Path(args.stress_factors), ("10%.layer8.left", "10%.layer8.right"))
    observed10 = apply_reversible(down, *factors10, expected_change=0.10)
    print("20 untouched tasks: preselected 10% Layer 8 validation", flush=True)
    after10 = generate_batches(model, tokenizer, problems, device=device,
                               batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    tests10 = parallel_execution(problems, after10, workers=args.workers, timeout=args.exec_timeout)
    score10, records10 = summarize(problems, baseline, before_tests, after10, tests10)
    save_json(destination / "progress.json", {"phase": "10pct_out_of_sample_finished",
                                                     "before": score10["before_passes"], "after": score10["after_passes"]})

    # The 1.5% comparator is tested only *after* the preselected candidate is frozen.
    with torch.no_grad():
        down.weight.copy_(original)
    factors15 = tensor_factors(Path(args.memit_factors), ("layer8.left", "layer8.right"))
    observed15 = apply_reversible(down, *factors15, expected_change=0.014984937, tolerance=0.00003)
    print("20 tasks: archived 1.5% Layer 8 MEMIT comparator", flush=True)
    after15 = generate_batches(model, tokenizer, problems, device=device,
                               batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    tests15 = parallel_execution(problems, after15, workers=args.workers, timeout=args.exec_timeout)
    score15, records15 = summarize(problems, baseline, before_tests, after15, tests15)
    with torch.no_grad():
        down.weight.copy_(original)

    report = {"status": "completed", "track": "final_holdout_validation", "base_model": BASE_MODEL,
              "dataset": DATA_URL, "source_commit": SOURCE_COMMIT, "held_out_until": "Session 008 validation",
              "task_ids": [p["task_id"] for p in problems],
              "hardware": {"device": "cpu", "threads": torch.get_num_threads(), "python": platform.python_version()},
              "edits": {"memit_10": {"layer": 8, "matrix": "mlp.down_proj", "observed_relative_delta_norm": observed10,
                                     "factor_sha256": fingerprint(Path(args.stress_factors))},
                        "memit_1p5": {"layer": 8, "matrix": "mlp.down_proj", "observed_relative_delta_norm": observed15,
                                       "factor_sha256": fingerprint(Path(args.memit_factors))}},
              "scores": {"memit_10": score10, "memit_1p5": score15}, "no_training": True,
              "caution": "The 20-task final holdout is consumed by this measurement; neither method was retargeted here"}
    predictions = {"task_ids": report["task_ids"],
                   "baseline_cases": [{"task_id": p["task_id"], "completion": code,
                                       "passed": bool(test["passed"]), "error": test["error"]}
                                      for p, code, test in zip(problems, baseline, before_tests, strict=True)],
                   "memit_10": records10, "memit_1p5": records15}
    save_report(destination, report, predictions)
    print("OUT-OF-SAMPLE VALIDATION", score10["before_passes"], "->", score10["after_passes"], flush=True)


def archived_baseline(previous_file: Path, validation_file: Path):
    """Reuse 50 prior measured baseline cases and the newly measured final 20."""
    archived = json.loads(previous_file.read_text(encoding="utf-8"))
    validation = json.loads(validation_file.read_text(encoding="utf-8"))
    historical = archived["variants"]["10%"]
    final = validation["baseline_cases"]
    expected = [f"HumanEval/{i}" for i in range(PREVIOUS_START, FINAL_START + FINAL_COUNT)]
    if ([r["task_id"] for r in historical] != expected[:PREVIOUS_COUNT]
            or [r["task_id"] for r in final] != expected[PREVIOUS_COUNT:]):
        raise ValueError("Baseline archive is incomplete or order does not match 70 HumanEval tasks")
    records = ([{"task_id": r["task_id"], "completion": r["before_completion"],
                "passed": r["before_passed"], "error": r["before_error"]} for r in historical]
               + final)
    return records


def evaluate_hybrid(args):
    import torch
    from safetensors.torch import save_file
    from .rome20 import BASE_MODEL, DATA_URL, fetch_problems
    from .rome_batch import generate_batches, parallel_execution
    from .weight_space import target_linear

    problems = contiguous_tasks(fetch_problems(), PREVIOUS_START, COMPARISON_COUNT)
    validation_report = json.loads(Path(args.validation_report).read_text(encoding="utf-8"))
    if (validation_report.get("status") != "completed"
            or validation_report.get("task_ids") != [f"HumanEval/{i}" for i in range(FINAL_START, 164)]):
        raise ValueError("The independent confirmation must finish before fusion is evaluated")
    baseline = archived_baseline(Path(args.previous_predictions), Path(args.validation_predictions))

    model, tokenizer, device = base_model_and_tokenizer()
    attn = target_linear(model, 8, "self_attn.o_proj")
    down = target_linear(model, 8, "mlp.down_proj")
    left_attn, right_attn = tensor_factors(Path(args.svd_factors),
                                           ("self_attn_o_proj.left", "self_attn_o_proj.right"))
    left_down, right_down = tensor_factors(Path(args.stress_factors),
                                           ("10%.layer8.left", "10%.layer8.right"))
    observed_attn = apply_reversible(attn, left_attn, right_attn,
                                     expected_change=0.1179615, tolerance=0.00004)
    observed_down = apply_reversible(down, left_down, right_down, expected_change=0.10)
    print("FUSION: SVD-erased Layer 8 attention o_proj + 10% MEMIT Layer 8 down_proj", flush=True)
    print("Executing all 70 HumanEval/94–163 hybrid completions; 4 sandbox workers", flush=True)
    completions = generate_batches(model, tokenizer, problems, device=device,
                                   batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    tests = parallel_execution(problems, completions, workers=args.workers, timeout=args.exec_timeout)
    base_completions = [r["completion"] for r in baseline]
    base_tests = [{"passed": r["passed"], "error": r["error"]} for r in baseline]
    score, records = summarize(problems, base_completions, base_tests, completions, tests)
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    save_file({"layer8.self_attn_o_proj.left": left_attn.clone(),
               "layer8.self_attn_o_proj.right": right_attn.clone(),
               "layer8.mlp_down_proj.left": left_down.clone(),
               "layer8.mlp_down_proj.right": right_down.clone()},
              str(destination / "hybrid_fusion_factors.safetensors"))
    report = {"status": "completed", "track": "svd_norm_fusion", "branch": "exp/05-svd-norm-fusion",
              "base_model": BASE_MODEL, "dataset": DATA_URL, "source_commit": SOURCE_COMMIT,
              "task_ids": [p["task_id"] for p in problems],
              "evaluation": {"new_hybrid_completions": 70, "historical_baseline_completions": 50,
                             "final_validation_baseline_completions": 20,
                             "sandbox": "network-disabled Docker, CPU multithreaded generation"},
              "factors": {"attention_matrix": "model.layers.8.self_attn.o_proj",
                          "attention_relative_change": observed_attn,
                          "mlp_matrix": "model.layers.8.mlp.down_proj",
                          "mlp_relative_change": observed_down,
                          "svd_factors_sha256": fingerprint(Path(args.svd_factors)),
                          "stress_factors_sha256": fingerprint(Path(args.stress_factors)),
                          "rank_attention": left_attn.shape[1], "rank_mlp": left_down.shape[1]},
              "scores": score, "no_training": True,
              "caution": "94–143 was previously examined for model selection; 144–163 was consumed by preselected 10% validation before this fusion test"}
    save_report(destination, report, {"task_ids": report["task_ids"], "cases": records})
    print("HYBRID 70", score["before_passes"], "->", score["after_passes"], flush=True)


def main():
    parser = argparse.ArgumentParser(description="CPU direct-weight validation and fusion")
    parser.add_argument("--mode", required=True, choices=("validate", "hybrid"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--exec-timeout", type=int, default=4)
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--stress-factors", default="experiments/exp03_norm_break_factors.safetensors")
    parser.add_argument("--memit-factors", default="experiments/exp04_memit_single_factors.safetensors")
    parser.add_argument("--svd-factors", default="experiments/exp02_svd_zeroing_factors.safetensors")
    parser.add_argument("--previous-predictions", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--validation-report", default="validation_artifact/report.json")
    parser.add_argument("--validation-predictions", default="validation_artifact/predictions.json")
    args = parser.parse_args()
    if not (1 <= args.batch_size <= 8 and 1 <= args.workers <= 8
            and 32 <= args.max_new_tokens <= 512 and 1 <= args.exec_timeout <= 30):
        parser.error("Invalid CPU generation or sandbox limits")
    from .sandbox_eval import require_sandbox
    import torch
    require_sandbox()
    torch.set_num_threads(4)
    torch.manual_seed(0)
    assert_reference_isolation(Path(args.source_progress))
    destination = Path(args.output_dir)
    if any((destination / name).exists() for name in
           ("report.json", "predictions.json", "hybrid_fusion_factors.safetensors")):
        raise FileExistsError("Refusing to overwrite existing experimental result files")
    if args.mode == "validate":
        validate_final(args)
    else:
        evaluate_hybrid(args)


if __name__ == "__main__":
    main()
