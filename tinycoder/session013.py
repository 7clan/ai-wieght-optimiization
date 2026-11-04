"""Session 013: paired, previously unused MBPP/MBPP+ generalization benchmark.

No model-generated code is executed by this module. Both the original MBPP
tests (as represented by EvalPlus's base cases) and MBPP+ expanded inputs are
evaluated using EvalPlus's checker *inside restricted Docker containers*.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import pickle
import re
import shutil
import subprocess
import tempfile
import uuid

MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B"
ANCHOR_BLOB_SHA = "7f872cd46918457c27d98f63230f1c9f47adb4c7"
SOURCE_COMMIT = "e100c628cd8fcf3c500e5c39070168e213b208aa"
BENCHMARK_SEED = "session013-mbppplus-independent-v1"
TASK_COUNT = 100
DOCKER_IMAGE = "tinycoder-session013-evalplus:0.3.1"
FAILURE_BINS = ("assertion_error", "boundary_edge_case", "unhandled_exception",
                "unclassified_logic_gap")


def git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def normalize_prompt(value: str) -> str:
    return " ".join(re.findall(r"\w+|[^\w\s]", value.casefold()))


def freeze_task_selection(mbpp_plus: dict, mbpp: dict, humaneval: list[dict],
                          *, task_count: int = TASK_COUNT) -> list[dict]:
    """Deterministic selection independent of any generated answer or score.

    The MBPP test split uses task IDs 11..510. All HumanEval 0..163 prompts
    are checked for exact normalized collisions, not semantic similarity.
    """
    seen = {normalize_prompt(item["prompt"]) for item in humaneval}
    candidates = []
    for task_id, problem in mbpp_plus.items():
        number = int(task_id.rsplit("/", 1)[-1])
        if not 11 <= number <= 510 or str(number) not in mbpp:
            continue
        if normalize_prompt(problem["prompt"]) in seen:
            continue
        if problem["task_id"] != task_id:
            raise ValueError("MBPP+ record identifier mismatch")
        # EvalPlus canonical solution is its documented prompt + completion.
        ast.parse(problem["prompt"] + problem["canonical_solution"])
        candidates.append(problem)
    candidates.sort(key=lambda p: (hashlib.sha256(
        f"{BENCHMARK_SEED}:{p['task_id']}".encode("utf-8")
    ).hexdigest(), p["task_id"]))
    if len(candidates) < task_count:
        raise ValueError(f"Only {len(candidates)} eligible MBPP+ test problems")
    selected = candidates[:task_count]
    if len({p["task_id"] for p in selected}) != task_count:
        raise ValueError("Duplicate MBPP identifiers")
    return selected


def validate_archived_anchor(path: Path) -> str:
    data = path.read_bytes()
    sha = git_blob_hash(data)
    if sha != ANCHOR_BLOB_SHA:
        raise ValueError(f"Archived 10% anchor Git blob mismatch: {sha}")
    return hashlib.sha256(data).hexdigest()


def docker_eval_command(input_dir: Path, result_dir: Path, name: str) -> list[str]:
    """No network, no writeable rootfs, no Linux privileges for generated code."""
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "128",
        "--memory", "1536m", "--cpus", "2", "--user", "65534:65534",
        "--tmpfs", "/tmp:rw,exec,nosuid,size=512m", "--env", "HOME=/tmp",
        "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=1",
        "--mount", f"type=bind,src={input_dir.resolve()},dst=/work,readonly",
        "--mount", f"type=bind,src={result_dir.resolve()},dst=/results",
        DOCKER_IMAGE, "python", "-I", "-B", "/work/worker.py",
        "/work/input.pkl", "/results/result.json",
    ]


def sandboxed_eval(selected: list[dict], completions: list[str],
                   *, workers: int = 2, chunk_size: int = 5) -> list[dict]:
    from .sandbox_eval import require_sandbox

    if len(selected) != TASK_COUNT or len(completions) != TASK_COUNT:
        raise ValueError("Benchmark must contain exactly 100 completions")
    require_sandbox()
    worker_src = Path(__file__).with_name("session013_evalplus_worker.py")
    if not worker_src.is_file():
        raise FileNotFoundError(worker_src)
    items = [{"problem": p, "solution": p["prompt"] + text,
              "syntax_valid": is_syntax_valid(p["prompt"] + text)}
             for p, text in zip(selected, completions, strict=True)]

    def run_chunk(chunk_index: int, chunk: list[dict]):
        with tempfile.TemporaryDirectory(prefix="session013_docker_") as folder:
            root = Path(folder)
            source_dir, result_dir = root / "source", root / "result"
            source_dir.mkdir(mode=0o755)
            result_dir.mkdir(mode=0o777)
            os.chmod(root, 0o755)
            os.chmod(result_dir, 0o777)
            payload = source_dir / "input.pkl"
            payload.write_bytes(pickle.dumps(chunk, protocol=4))
            shutil.copyfile(worker_src, source_dir / "worker.py")
            for file in source_dir.iterdir():
                os.chmod(file, 0o644)
            name = "tinycoder-mbpp-" + uuid.uuid4().hex[:16]
            cmd = docker_eval_command(source_dir, result_dir, name)
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
            except subprocess.TimeoutExpired as exc:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                               timeout=15, check=False)
                raise RuntimeError(f"MBPP+ sandbox chunk {chunk_index} timed out") from exc
            if proc.returncode:
                raise RuntimeError(f"MBPP+ sandbox chunk {chunk_index} exited "
                                   f"{proc.returncode}: {proc.stderr[-1500:]}")
            result_file = result_dir / "result.json"
            if not result_file.is_file():
                raise RuntimeError(f"Missing sandbox result for chunk {chunk_index}")
            result = json.loads(result_file.read_text(encoding="utf-8"))
            if ([x["task_id"] for x in result] !=
                    [x["problem"]["task_id"] for x in chunk]):
                raise RuntimeError("Sandbox output IDs/order mismatch")
            print(f"  Docker MBPP+ {min((chunk_index + 1) * chunk_size, TASK_COUNT)}/{TASK_COUNT}",
                  flush=True)
            return result

    chunks = [items[i:i + chunk_size] for i in range(0, TASK_COUNT, chunk_size)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        nested = list(pool.map(lambda pair: run_chunk(*pair), enumerate(chunks)))
    return [item for group in nested for item in group]


def is_syntax_valid(solution: str) -> bool:
    try:
        ast.parse(solution)
        return True
    except (SyntaxError, ValueError, MemoryError):
        return False


def summarize(records: list[dict]) -> dict:
    if len(records) != TASK_COUNT or len({r["task_id"] for r in records}) != TASK_COUNT:
        raise ValueError("Invalid 100-task result set")
    passed_base = [r["task_id"] for r in records if r["base_pass"]]
    passed_plus = [r["task_id"] for r in records if r["plus_pass"]]
    syntax = [r["task_id"] for r in records if r["syntax_valid"]]
    bins = {kind: [r["task_id"] for r in records if r["failure_bin"] == kind]
            for kind in FAILURE_BINS}
    bins["syntax_invalid"] = [r["task_id"] for r in records if r["failure_bin"] == "syntax_invalid"]
    if sum(len(ids) for ids in bins.values()) + len(passed_plus) != TASK_COUNT:
        raise ValueError("Failure taxonomy is not exhaustive/disjoint")
    if not set(passed_plus).issubset(set(passed_base)):
        raise ValueError("Expanded MBPP+ pass without base suite pass")
    return {
        "count": TASK_COUNT,
        "base_pass_count": len(passed_base), "base_pass_at_1": len(passed_base) / TASK_COUNT,
        "plus_pass_count": len(passed_plus), "plus_pass_at_1": len(passed_plus) / TASK_COUNT,
        "syntax_valid_count": len(syntax), "syntax_validity": len(syntax) / TASK_COUNT,
        "passed_base_ids": passed_base, "passed_plus_ids": passed_plus,
        "failed_base_ids": [r["task_id"] for r in records if not r["base_pass"]],
        "failed_plus_ids": [r["task_id"] for r in records if not r["plus_pass"]],
        "syntax_valid_ids": syntax,
        "failure_taxonomy": {key: {"count": len(ids), "task_ids": ids}
                             for key, ids in bins.items()},
    }


def run(args) -> None:
    import importlib.metadata
    import torch
    from evalplus.data import get_mbpp, get_mbpp_plus, get_mbpp_plus_hash
    from .fusion_validation import (apply_reversible, base_model_and_tokenizer,
                                    tensor_factors)
    from .rome20 import fetch_problems, save_json
    from .rome_batch import generate_batches
    from .weight_space import target_linear

    if args.track not in ("baseline", "anchor"):
        raise ValueError("Unknown evaluation track")
    if args.max_new_tokens != 160 or args.batch_size != 4 or args.workers != 2:
        raise ValueError("Session 013 comparison settings are frozen: 160 tokens, batch4, Docker2")
    torch.manual_seed(0)
    torch.set_num_threads(4)
    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite existing benchmark results")
    out.mkdir(parents=True, exist_ok=True)

    factor_sha256 = validate_archived_anchor(Path(args.anchor_factors))
    mbpp, plus, humaneval = get_mbpp(), get_mbpp_plus(), fetch_problems()
    selected = freeze_task_selection(plus, mbpp, humaneval)
    ordered_ids = [p["task_id"] for p in selected]
    original_overlaps = [p["task_id"] for p in selected
                         if normalize_prompt(p["prompt"]) in
                         {normalize_prompt(h["prompt"]) for h in humaneval}]
    if original_overlaps:
        raise AssertionError("HumanEval prompt collision")

    manifest = {
        "dataset": "EvalPlus MBPP+ v0.2.0 (base MBPP + expanded tests)",
        "evalplus_version": importlib.metadata.version("evalplus"),
        "dataset_md5": get_mbpp_plus_hash(),
        "selection_seed": BENCHMARK_SEED,
        "sample_size": TASK_COUNT,
        "task_ids": ordered_ids,
        "task_prompt_sha256": {p["task_id"]: hashlib.sha256(p["prompt"].encode()).hexdigest()
                               for p in selected},
        "eligible_range": "MBPP test-split ID 11..510",
        "prior_experimental_overlap": [],
        "human_eval_normalized_prompt_overlap": original_overlaps,
        "pretraining_nonexposure_guaranteed": False,
    }
    save_json(out / "manifest.json", manifest)
    model, tokenizer, device = base_model_and_tokenizer()
    if getattr(model.config, "_name_or_path", MODEL_ID) != MODEL_ID or len(model.model.layers) != 24:
        raise ValueError("Unexpected model or layer count; 0.5B baseline required")
    n_params = sum(param.numel() for param in model.parameters())
    observed_edit = 0.0
    if args.track == "anchor":
        factors = tensor_factors(Path(args.anchor_factors),
                                 ("10%.layer8.left", "10%.layer8.right"))
        observed_edit = apply_reversible(target_linear(model, 8, "mlp.down_proj"),
                                         *factors, expected_change=0.10)
    outputs = generate_batches(model, tokenizer, selected, device=device,
                               batch_size=args.batch_size, max_new_tokens=args.max_new_tokens)
    del model
    raw_predictions = [{"task_id": p["task_id"], "prompt": p["prompt"],
                        "completion": completion, "syntax_valid": is_syntax_valid(p["prompt"]+completion)}
                       for p, completion in zip(selected, outputs, strict=True)]
    save_json(out / "predictions.json", raw_predictions)
    results = sandboxed_eval(selected, outputs, workers=args.workers)
    for generated, result in zip(raw_predictions, results, strict=True):
        if generated["task_id"] != result["task_id"]:
            raise RuntimeError("Evaluation lost task alignment")
    metrics = summarize(results)
    report = {
        "status": "completed", "session": "013", "track": args.track,
        "model": MODEL_ID, "parameter_count": n_params, "device": "cpu",
        "threads": 4, "max_new_tokens": args.max_new_tokens,
        "batch_size": args.batch_size, "temperature": 0,
        "training_steps": 0, "only_modified_matrix": "layer8.mlp.down_proj" if args.track == "anchor" else None,
        "factor_source_commit": SOURCE_COMMIT, "factor_git_blob_sha": ANCHOR_BLOB_SHA,
        "factor_sha256": factor_sha256, "observed_relative_frobenius": observed_edit,
        "dataset_manifest": manifest, "metrics": metrics, "task_results": results,
        "execution_sandbox": "network-disabled, read-only, unprivileged Docker with EvalPlus oracle",
        "taxonomy_limitations": "Expanded-test-only failure is an edge-case proxy; independent runtime probe distinguishes exceptions from returned wrong results; remaining cases unclassified.",
    }
    save_json(out / "report.json", report)
    print(json.dumps({"track": args.track,
                      "base_passes": metrics["base_pass_count"],
                      "plus_passes": metrics["plus_pass_count"],
                      "syntax_valid": metrics["syntax_valid_count"]}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", choices=("baseline", "anchor"), required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--anchor-factors", default="experiments/exp03_norm_break_factors.safetensors")
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
