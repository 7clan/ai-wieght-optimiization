"""Session 010: Docker diagnostic taxonomy and direct rank-eight weight surgery.

No gradients, optimizer steps, LoRA or unsandboxed model-code execution.
Taxonomy labels are conservative evidence proxies, never ground-truth bug labels.
The prior 70-task benchmark has already been consumed by earlier sessions.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from .attention_steering import source_failures, collect_attn
from .fusion_validation import apply_reversible, archived_baseline, base_model_and_tokenizer, contiguous_tasks, summarize, tensor_factors
from .rome20 import BASE_MODEL, DATA_URL, fetch_problems, save_json
from .sandbox_eval import docker_command, require_sandbox

SOURCE_COMMIT = "e100c628cd8fcf3c500e5c39070168e213b208aa"
SESSION009_RESULTS = "c9ba781883efb2d0a7c0e4d2e0f4cf0b6a5310c7"
RANK = 8
LAYERS = (12, 13, 15)
ATTENTION_CAP = .015
BINS = ("off_by_one_index_boundary", "wrong_output_type", "missing_edge_case", "truncation_or_context")


def valid_failed_cases(problems, predictions: dict) -> tuple[list[tuple[dict, dict]], list[str]]:
    expected = [f"HumanEval/{idx}" for idx in range(94, 164)]
    cases = predictions.get("cases", [])
    if predictions.get("task_ids") != expected or [x["task_id"] for x in cases] != expected:
        raise ValueError("Session009 predictions have unexpected HumanEval IDs/order")
    lookup = {p["task_id"]: p for p in problems}
    failures, syntax_valid = [], []
    for record in cases:
        problem = lookup[record["task_id"]]
        try:
            ast.parse(problem["prompt"] + record["after_completion"])
        except SyntaxError:
            continue
        syntax_valid.append(record["task_id"])
        if not record["after_passed"]:
            failures.append((problem, record))
    return failures, syntax_valid


def diagnostic_execution(problem: dict, completion: str, timeout: int = 4) -> dict:
    """Capture a bounded traceback using the SAME restricted Docker runner."""
    source = (problem["prompt"] + completion + "\n\n" + problem["test"]
              + "\n\ncheck(globals()[" + repr(problem["entry_point"]) + "])\n")
    if len(source) > 100000:
        raise ValueError("Oversized diagnostic code")
    with tempfile.TemporaryDirectory(prefix="tinycoder_diagnose_") as folder:
        os.chmod(folder, 0o755)
        script = Path(folder) / "solution.py"
        script.write_text(source, encoding="utf-8")
        os.chmod(script, 0o644)
        name = "tinycoder-" + uuid.uuid4().hex[:16]
        try:
            run = subprocess.run(docker_command(folder, name), capture_output=True,
                                 timeout=timeout + 4, check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           timeout=10, check=False)
            return {"outcome": "timeout", "exception_type": "Timeout",
                    "failing_assertion": None, "stderr_tail": ""}
        if run.returncode == 125:
            raise RuntimeError("Docker rejected restricted diagnostic execution")
        stderr = run.stderr.decode("utf-8", errors="replace")[-2500:]
        matches = re.findall(r'File "/work/solution.py", line (\d+)', stderr)
        lineno = int(matches[-1]) if matches else None
        lines = source.splitlines()
        failing = lines[lineno - 1].strip()[:500] if lineno and 1 <= lineno <= len(lines) else None
        exception = re.findall(r"(?m)^([A-Za-z_]+(?:Error|Exception))(?::|$)", stderr)
        return {"outcome": "passed" if run.returncode == 0 else "failed",
                "exception_type": exception[-1] if exception else None,
                "failing_assertion": failing if failing and failing.startswith("assert ") else None,
                "stderr_tail": stderr[-1200:]}


def is_blank_entry_implementation(problem: dict, completion: str) -> bool:
    try:
        tree = ast.parse(problem["prompt"] + completion)
    except SyntaxError:
        return False
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == problem["entry_point"]]
    if not defs:
        return False
    last = defs[-1]
    statements = [n for n in last.body if not (isinstance(n, ast.Expr)
                  and isinstance(n.value, (ast.Constant, ast.Str)))]
    return not statements or all(isinstance(n, ast.Pass) for n in statements)


def classify_failure(problem: dict, completion: str, execution: dict) -> dict:
    """Assign at most one of four requested evidence-based bins or unclassified."""
    exc = execution["exception_type"]
    assertion = execution["failing_assertion"] or ""
    if exc == "IndexError":
        chosen, reason = BINS[0], "Observed IndexError in restricted execution"
    elif is_blank_entry_implementation(problem, completion):
        chosen, reason = BINS[1], "Entry point has no value-producing implementation (implicit None)"
    elif re.search(r"\(\s*(?:\[\s*\]|-\d+|None|['\"]['\"])", assertion):
        chosen, reason = BINS[2], "First failed assertion explicitly exercises an empty/negative/None input"
    elif (execution["outcome"] == "timeout" or
          (completion.count("def " + problem["entry_point"] + "(") >= 1 and
           completion.rstrip().endswith(("pass", "#", "\"\"\"")))):
        chosen, reason = BINS[3], "Timeout or likely generation-budget truncation; context expiry unverified"
    else:
        chosen, reason = None, "Mismatch/exception does not establish one of the requested four causes"
    return {"category": chosen, "evidence": reason,
            "certainty": "observed" if exc == "IndexError" or execution["outcome"] == "timeout"
                         else "heuristic" if chosen else "unclassified"}


def classify_cases(problems, records, *, workers=4, expected_syntax=None):
    failing, valid_ids = valid_failed_cases(problems, records)
    if expected_syntax is not None and len(valid_ids) != expected_syntax:
        raise ValueError(f"Expected {expected_syntax} syntax-valid completions, got {len(valid_ids)}")

    def one(item):
        problem, record = item
        result = diagnostic_execution(problem, record["after_completion"])
        if result["outcome"] == "passed":
            raise ValueError("Previously failed completion passed on diagnostic replay")
        classification = classify_failure(problem, record["after_completion"], result)
        return {"task_id": problem["task_id"], "original_error": record["after_error"],
                "diagnostic": result, **classification}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        details = list(pool.map(one, failing))
    groups = {key: [item["task_id"] for item in details if item["category"] == key] for key in BINS}
    unmatched = [item["task_id"] for item in details if item["category"] is None]
    if sum(map(len, groups.values())) + len(unmatched) != len(failing):
        raise RuntimeError("Taxonomy accounting mismatch")
    return {"syntax_valid_count": len(valid_ids), "syntax_valid_ids": valid_ids,
            "failed_syntax_valid_count": len(failing),
            "syntax_valid_passed_count": len(valid_ids) - len(failing),
            "bins": {key: {"count": len(ids), "task_ids": ids} for key, ids in groups.items()},
            "unclassified_count": len(unmatched), "unclassified_ids": unmatched,
            "cases": details, "method": "Replayed complete official assertions in network-disabled read-only Docker; four conservative primary classifications, with unmatched cases separate",
            "limitations": "Assertions often lack an expected/actual diagnostic. Inferred categories are heuristic; semantic algorithm errors need not fit the four bins. 160-token generation cap is not context-window expiry."}


def source_risk_labels(problem: dict) -> dict[str, bool]:
    """Pre-94 canonical AST *proxies* for boundary/type-risk directions."""
    tree = ast.parse(problem["prompt"] + problem["canonical_solution"])
    nodes = list(ast.walk(tree))
    boundary = any(isinstance(n, (ast.Subscript, ast.For, ast.While, ast.Compare)) for n in nodes)
    return_types = {type(n.value).__name__ for n in nodes if isinstance(n, ast.Return) and n.value}
    type_risk = bool(return_types & {"List", "Tuple", "Dict", "Set", "ListComp", "DictComp", "IfExp"})
    type_risk |= len(return_types) >= 2
    return {"boundary_proxy": boundary, "return_type_proxy": type_risk}


def derive_svd_rank8(weight, failed_inputs, teacher_inputs, labels, *, rank=RANK, cap=ATTENTION_CAP):
    """Ridge-regression closed-form edit, truncated to exact rank 8 by small SVD."""
    import torch

    if len(failed_inputs) != 20 or len(teacher_inputs) != 20 or len(labels) != 20:
        raise ValueError("Must use exactly 20 original reference/failure pairs")
    w = weight.detach().float().cpu()
    keys = torch.stack(failed_inputs, 1).float().cpu()
    teachers = torch.stack(teacher_inputs, 1).float().cpu()
    if keys.shape != (w.shape[1], 20) or teachers.shape != keys.shape:
        raise ValueError("Misaligned o_proj input dimensions")
    importance = torch.tensor([1.0 + 1.0*lab["boundary_proxy"] + 1.0*lab["return_type_proxy"]
                               for lab in labels], dtype=torch.float32)
    scale = torch.sqrt(importance)[None, :]
    k = keys * scale
    desired = (w @ (teachers - keys)) * scale
    gram = k.T @ k
    ridge = max(float(gram.diag().mean()) * .0001, .0001)
    solved = torch.linalg.solve(gram + ridge * torch.eye(20), torch.eye(20))
    left_full = desired @ solved
    # Delta = left_full @ k.T (at most rank 20). Thin QR + 20x20 SVD
    # computes the top-eight SVD components without an 896x896 full SVD.
    qu, ru = torch.linalg.qr(left_full, mode="reduced")
    qv, rv = torch.linalg.qr(k, mode="reduced")
    u, singular, vh = torch.linalg.svd(ru @ rv.T, full_matrices=False)
    if int((singular > 1e-7).sum().item()) < rank:
        raise ValueError("Reference pairs do not span eight edit directions")
    root = singular[:rank].sqrt()
    left = ((qu @ u[:, :rank]) * root[None, :]).contiguous()
    right = (root[:, None] * (vh[:rank, :] @ qv.T)).contiguous()
    norm_w = torch.linalg.vector_norm(w)
    raw_delta = left @ right
    proposal = float((torch.linalg.vector_norm(raw_delta) / norm_w).item())
    capped = min(1.0, cap / proposal) if proposal else 1.0
    left = (left * capped).contiguous()
    observed = float((torch.linalg.vector_norm(left @ right) / norm_w).item())
    if not torch.isfinite(left).all() or not torch.isfinite(right).all() or observed > cap + 1e-6:
        raise RuntimeError("Non-finite or over-budget high-rank factors")
    return left, right, {"rank": rank, "method": "weighted multi-key ridge solution, rank-8 thin-QR SVD projection",
                         "ridge": ridge, "uncapped_relative_norm": proposal, "cap_scale": capped,
                         "expected_relative_norm": observed,
                         "singular_values_top8": singular[:rank].tolist(),
                         "source_proxy_counts": {k: sum(lab[k] for lab in labels) for k in labels[0]},
                         "source_weights": importance.tolist()}


def run_taxonomy(args):
    problems = fetch_problems()
    predictions = json.loads(Path(args.prior_predictions).read_text(encoding="utf-8"))
    result = classify_cases(problems, predictions, workers=args.workers, expected_syntax=19)
    result.update({"status": "completed", "session": "010", "source_predictions_commit": SESSION009_RESULTS,
                   "source_path": "experiments/attn_steering_predictions.json",
                   "task_range": [94, 163], "four_requested_bins": list(BINS)})
    save_json(Path(args.output_dir) / "assertion_failure_taxonomy.json", result)
    print("SESSION010 TAXONOMY", {k: v["count"] for k, v in result["bins"].items()},
          "unclassified", result["unclassified_count"], flush=True)


def run_surgery(args):
    import torch
    from safetensors.torch import save_file
    from .rome_batch import generate_batches, parallel_execution
    from .weight_space import target_linear, get_layer_weights, apply_weight_edit

    problems = fetch_problems()
    original = json.loads(Path(args.source_progress).read_text(encoding="utf-8"))
    examples = source_failures(problems, original)
    model, tokenizer, device = base_model_and_tokenizer()
    captures = []
    for i, problem in enumerate(examples, 1):
        failed, _ = collect_attn(model, tokenizer, problem["prompt"], layers=LAYERS)
        teacher, _ = collect_attn(model, tokenizer, problem["prompt"] + problem["canonical_solution"], layers=LAYERS)
        captures.append({"failed": failed, "teacher": teacher, "labels": source_risk_labels(problem)})
        print(f"  original-reference attention pair {i}/20", flush=True)
    label_vectors = [item["labels"] for item in captures]
    if (sum(x["boundary_proxy"] for x in label_vectors) < 2 or
            sum(x["return_type_proxy"] for x in label_vectors) < 2):
        raise RuntimeError("Insufficient original failure/reference source proxy diversity")

    frozen = {}
    factors = {}
    for layer in LAYERS:
        before, inspection = get_layer_weights(model, layer, "self_attn.o_proj")
        left, right, metadata = derive_svd_rank8(
            before, [x["failed"][layer]["input"] for x in captures],
            [x["teacher"][layer]["input"] for x in captures], label_vectors)
        apply_weight_edit(model, layer, "self_attn.o_proj", left, right)
        observed = float((torch.linalg.vector_norm((target_linear(model, layer, "self_attn.o_proj").weight - before).float())
                          / torch.linalg.vector_norm(before.float())).item())
        if observed > ATTENTION_CAP + 1e-6:
            raise RuntimeError("Observed rank-eight attention update exceeded 1.5%")
        frozen[str(layer)] = {"inspection": inspection, **metadata, "observed_relative_norm": observed}
        factors[f"layer{layer}.self_attn_o_proj.left"] = left.cpu().contiguous()
        factors[f"layer{layer}.self_attn_o_proj.right"] = right.cpu().contiguous()

    source_file = Path(args.stress_factors)
    old_left, old_right = tensor_factors(source_file, ("10%.layer8.left", "10%.layer8.right"))
    observed_mlp = apply_reversible(target_linear(model, 8, "mlp.down_proj"),
                                    old_left, old_right, expected_change=.10)
    factors["layer8.mlp_down_proj.left"] = old_left.cpu().contiguous()
    factors["layer8.mlp_down_proj.right"] = old_right.cpu().contiguous()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    save_file(factors, str(output / "highrank_logic_factors.safetensors"))
    factor_report = {"status": "frozen", "source_commit": SOURCE_COMMIT,
                     "source_reference_ids": [p["task_id"] for p in examples],
                     "source_proxy_definitions": {
                         "boundary_proxy": "Source AST has a subscript, loop, or comparison",
                         "return_type_proxy": "Source AST returns collections or multiple expression forms"},
                     "layers": list(LAYERS), "factor_metadata": frozen,
                     "archived_mlp_relative_norm": observed_mlp,
                     "archived_mlp_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
                     "rank_per_matrix": RANK, "cap_per_attention_matrix": ATTENTION_CAP,
                     "no_backprop": True,
                     "limitations": "Source-AST risk labels are proxies, not measured off-by-one or type-mismatch causal directions"}
    save_json(output / "highrank_factor_report.json", factor_report)

    holdout = contiguous_tasks(problems, 94, 70)
    baseline = archived_baseline(Path(args.previous_predictions), Path(args.validation_predictions))
    print("Generate 70 greedy completions with fixed three-layer rank-8 factors", flush=True)
    completions = generate_batches(model, tokenizer, holdout, device=device,
                                   batch_size=args.batch_size, max_new_tokens=160)
    results = parallel_execution(holdout, completions, workers=args.workers, timeout=4)
    summary, cases = summarize(holdout, [x["completion"] for x in baseline],
                               [{"passed": x["passed"], "error": x["error"]} for x in baseline],
                               completions, results)
    new_predictions = {"task_ids": [p["task_id"] for p in holdout], "cases": cases}
    save_json(output / "highrank_logic_predictions.json", new_predictions)
    prior_report = json.loads(Path(args.prior_report).read_text(encoding="utf-8"))
    prior_scores = prior_report["scores"]
    if (prior_report.get("status") != "completed" or prior_report.get("session") != "009"
            or prior_report.get("task_ids") != new_predictions["task_ids"]
            or prior_scores.get("after_passes") != 3 or prior_scores["syntax_after"]["valid"] != 19):
        raise ValueError("Session009 historical comparison identity mismatch")
    shifted = classify_cases(problems, new_predictions, workers=args.workers)
    old_taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    taxonomy_shift = {"prior_syntax_valid_failures": old_taxonomy["failed_syntax_valid_count"],
                      "after_syntax_valid_failures": shifted["failed_syntax_valid_count"],
                      "before_bins": old_taxonomy["bins"], "after_bins": shifted["bins"],
                      "before_unclassified": old_taxonomy["unclassified_count"],
                      "after_unclassified": shifted["unclassified_count"],
                      "after_details": shifted["cases"], "warning": shifted["limitations"]}
    save_json(output / "highrank_taxonomy_shift.json", taxonomy_shift)
    report = {"status": "completed", "session": "010", "branch": "exp/07-highrank-logic-boost",
              "base_model": BASE_MODEL, "dataset": DATA_URL,
              "source_commit": SOURCE_COMMIT, "source_predictions_commit": SESSION009_RESULTS,
              "task_ids": [p["task_id"] for p in holdout],
              "scores": summary, "layer_norms": {k: v["observed_relative_norm"] for k,v in frozen.items()},
              "session009_hybrid_comparison": {
                  "prior_passes": prior_scores["after_passes"],
                  "prior_syntax_valid": prior_scores["syntax_after"]["valid"],
                  "pass_at_1_percentage_point_delta": (summary["after_passes"] - prior_scores["after_passes"]) * 100/70,
                  "syntax_valid_count_delta": summary["syntax_after"]["valid"] - prior_scores["syntax_after"]["valid"]},
              "applied_archived_mlp_relative_norm": observed_mlp,
              "factors": "experiments/highrank_logic_factors.safetensors",
              "taxonomy_shift": taxonomy_shift,
              "no_training": True,
              "caution": "Previously consumed HumanEval/94–163; in-sample exploratory comparison, not independent validation. Editing directions use unvalidated AST proxies."}
    save_json(output / "highrank_logic_report.json", report)
    print("SESSION010 PASS@1", summary["before_passes"], "->", summary["after_passes"],
          "SYNTAX", summary["syntax_before"]["valid"], "->", summary["syntax_after"]["valid"], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("taxonomy", "surgery"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prior-predictions", default="prior/experiments/attn_steering_predictions.json")
    parser.add_argument("--prior-report", default="prior/experiments/attn_steering_report.json")
    parser.add_argument("--source-progress", default="experiments/2026-11-04-rome20/progress.json")
    parser.add_argument("--stress-factors", default="experiments/exp03_norm_break_factors.safetensors")
    parser.add_argument("--previous-predictions", default="experiments/exp03_norm_break_predictions.json")
    parser.add_argument("--validation-predictions", default="experiments/final_holdout_validation_predictions.json")
    parser.add_argument("--taxonomy", default="frozen_taxonomy/assertion_failure_taxonomy.json")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not (1 <= args.workers <= 8 and 1 <= args.batch_size <= 8):
        parser.error("workers and batch-size must lie within 1..8")
    require_sandbox()
    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to replace previous experiment artifacts")
    output.mkdir(parents=True, exist_ok=True)
    if args.mode == "taxonomy":
        run_taxonomy(args)
    else:
        import torch
        torch.set_num_threads(4)
        torch.manual_seed(0)
        run_surgery(args)


if __name__ == "__main__":
    main()
