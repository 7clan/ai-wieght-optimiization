"""Session014: orthogonal rank32 edits and mode-gated attention output hooks.

No training or gradients. No generated code executes outside restricted Docker.
The UI/API tasks are explicitly authored here, not represented as public MBPP+.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import pickle
import re
import shutil
import subprocess
import tempfile
import uuid

from .session014_fixtures import (TRIGGER_KEYWORDS, make_reference_trajectories,
                                 make_web_tasks, sha256_json)

MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B"
EXCLUDED_IDS_FILE = Path("data/session014_excluded_mbpp_ids.json")
MBPP_COUNT, WEB_COUNT, TOTAL_COUNT = 50, 50, 100
SELECTION_SEED = "session014-mbppplus-disjoint-v1"
SOURCE_LAYER8, SOURCE_LAYER16 = 8, 16
HOOK_LAYERS = (12, 18)
SUBSPACE_RANK = 32
CAP_FROBENIUS = 0.015
ALPHAS = (0.25, 0.75, 1.25)
TRACKS = ("baseline", "static", "dynamic-0.25", "dynamic-0.75", "dynamic-1.25",
          "hybrid-0.25", "hybrid-0.75", "hybrid-1.25")
DOCKER_MBPP = "tinycoder-session014-mbpp:0.3.1"
DOCKER_WEB = "tinycoder-session014-web:1"


def normalized(s: str) -> str:
    return " ".join(re.findall(r"\w+|[^\w\s]", s.casefold()))


def select_mbpp(plus, original, humaneval, exclusions, count=MBPP_COUNT):
    forbidden = set(exclusions)
    human_prompts = {normalized(p["prompt"]) for p in humaneval}
    options = [p for key,p in plus.items()
               if key not in forbidden and 11 <= int(key.rsplit("/",1)[1]) <= 510
               and key.rsplit("/",1)[1] in original
               and normalized(p["prompt"]) not in human_prompts]
    options.sort(key=lambda p: (hashlib.sha256((SELECTION_SEED + ":" + p["task_id"]).encode()).hexdigest(),p["task_id"]))
    if len(options) < count:
        raise ValueError("Not enough fresh MBPP+ tasks")
    chosen = options[:count]
    if len({x["task_id"] for x in chosen}) != count:
        raise ValueError("Duplicate benchmark ID")
    return chosen


def frozen_tasks():
    from evalplus.data import get_mbpp_plus, get_mbpp_plus_hash
    from evalplus.data.mbpp import get_mbpp
    from .rome20 import fetch_problems

    source = json.loads(EXCLUDED_IDS_FILE.read_text(encoding="utf-8"))
    if len(source["ids"]) != 100 or len(set(source["ids"])) != 100:
        raise ValueError("Session013 exclusions were altered")
    selected = select_mbpp(get_mbpp_plus(), get_mbpp(), fetch_problems(), source["ids"])
    web = make_web_tasks()
    sources = make_reference_trajectories()
    original_test_text = {normalized(p["prompt"]) for p in selected}
    source_text = {normalized(p["prompt"]) for p in sources}
    if (len(source_text) != 50 or
            any(normalized(t["prompt"]) in source_text or normalized(t["prompt"]) in original_test_text
                for t in web) or
            set(p["task_id"] for p in selected) & set(source["ids"])):
        raise ValueError("Source/benchmark prompt leakage or prior MBPP reuse")
    manifest = {
        "model": MODEL_ID,
        "mbpp_plus_count": 50, "web_authored_count": 50, "total": TOTAL_COUNT,
        "mbpp_plus_dataset_md5": get_mbpp_plus_hash(),
        "evalplus_version": importlib.metadata.version("evalplus"),
        "selection_seed": SELECTION_SEED, "excluded_session013_task_ids_sha256": sha256_json(source["ids"]),
        "mbpp_task_ids": [x["task_id"] for x in selected],
        "web_task_ids": [x["task_id"] for x in web],
        "source_task_ids": [x["task_id"] for x in sources],
        "web_fixture_sha256": sha256_json(web),
        "source_fixture_sha256": sha256_json(sources),
        "mbpp_prompt_sha256": {x["task_id"]: hashlib.sha256(x["prompt"].encode()).hexdigest() for x in selected},
        "nonexposure_in_pretraining_proven": False,
        "web_dataset_provenance": "Custom, template-generated test tasks; not an external standardized benchmark",
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    return selected, web, sources, manifest


def docker_command(image: str, source_dir: Path, output_dir: Path, name: str, is_web: bool):
    cmd = ["docker", "run", "--rm", "--name", name,
           "--network", "none", "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--pids-limit", "128",
           "--memory", "1536m", "--cpus", "2", "--user", "65534:65534",
           "--tmpfs", "/tmp:rw,exec,nosuid,size=512m", "--env", "HOME=/tmp",
           "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=1",
           "--mount", f"type=bind,src={source_dir.resolve()},dst=/work,readonly",
           "--mount", f"type=bind,src={output_dir.resolve()},dst=/results", image]
    if is_web:
        cmd.extend(["/work/input.json", "/results/result.json"])
    else:
        cmd.extend(["python", "-I", "-B", "/work/worker.py", "/work/input.pkl", "/results/result.json"])
    return cmd


def _sandbox_chunk(items, chunk_index, *, web):
    with tempfile.TemporaryDirectory(prefix="session014_docker_") as directory:
        root = Path(directory)
        inp, out = root / "in", root / "out"
        inp.mkdir(mode=0o755)
        out.mkdir(mode=0o777)
        os.chmod(root, 0o755)
        os.chmod(out, 0o777)
        if web:
            data = inp / "input.json"
            data.write_text(json.dumps(items), encoding="utf-8")
            image = DOCKER_WEB
        else:
            data = inp / "input.pkl"
            data.write_bytes(pickle.dumps(items, protocol=4))
            worker = inp / "worker.py"
            shutil.copyfile(Path(__file__).with_name("session014_mbpp_worker.py"), worker)
            os.chmod(worker, 0o644)
            image = DOCKER_MBPP
        os.chmod(data, 0o644)
        name = "tinycoder-s014-" + uuid.uuid4().hex[:16]
        cmd = docker_command(image, inp, out, name, web)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           text=True, timeout=15, check=False)
            raise RuntimeError(f"Docker chunk {chunk_index} timed out") from e
        if proc.returncode:
            raise RuntimeError(f"Docker {image} chunk {chunk_index}: {proc.stderr[-1300:]}")
        output = out / "result.json"
        if not output.exists():
            raise RuntimeError("Docker did not write an evaluation result")
        results = json.loads(output.read_text(encoding="utf-8"))
        if [r["task_id"] for r in results] != [x["task_id"] if web else x["problem"]["task_id"] for x in items]:
            raise RuntimeError("Docker lost task ordering")
        return results


def docker_evaluate(tasks, completions, *, web, workers=2):
    from .sandbox_eval import require_sandbox
    require_sandbox()
    if len(tasks) != len(completions) or not tasks:
        raise ValueError("Mismatched scoring tasks/completions")
    if web:
        entries = [{"task_id":task["task_id"], "task":task,
                    "solution":task["prompt"] + completion}
                   for task,completion in zip(tasks,completions, strict=True)]
    else:
        entries = [{"problem":problem, "solution":problem["prompt"] + completion,
                    "syntax_valid": syntax_python(problem["prompt"] + completion)}
                   for problem,completion in zip(tasks,completions, strict=True)]
    chunks = [entries[i:i+5] for i in range(0, len(entries), 5)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda pair: _sandbox_chunk(pair[1], pair[0], web=web), enumerate(chunks)))
    return [row for chunk in records for row in chunk]


def syntax_python(code):
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError, MemoryError):
        return False


def validate_references(sources, web):
    """All references are actually executed in Docker before activation capture."""
    source_tasks = []
    for source in sources:
        if source["mode"] == "ui":
            tests = [{"props": {"value": "test"}, "contains": ["<div", "test"]}]
        else:
            n = int(source["task_id"].split("/")[-1])
            tests = [{"method": "get", "path": f"/training-{n}", "body": None,
                      "expected": {"value": n}}]
        source_tasks.append({**source, "tests": tests})
    for label, collection in (("source", source_tasks), ("web", web)):
        records = docker_evaluate(collection, [t["reference"][len(t["prompt"]):]
                                               for t in collection], web=True)
        failed = [r for r in records if not r["passed"]]
        if failed:
            raise RuntimeError(f"Authored {label} references failed Docker verification: {failed[:3]}")
        print(f"Verified {len(records)} {label} references in isolated Docker", flush=True)


def _torch_model():
    import torch
    from .fusion_validation import base_model_and_tokenizer
    torch.manual_seed(0)
    torch.set_num_threads(4)
    model, tokenizer, _ = base_model_and_tokenizer()
    if (getattr(model.config, "_name_or_path", MODEL_ID) != MODEL_ID
            or getattr(model.config, "hidden_size", None) != 896
            or len(model.model.layers) != 24
            or sum(x.numel() for x in model.parameters()) != 494032768):
        raise ValueError("Not the fixed 0.5B Qwen2.5-Coder architecture")
    if any(x.requires_grad is False for x in model.parameters()):
        pass  # Loaded checkpoint may have frozen parameters; no gradient path is used.
    model.requires_grad_(False)
    return model, tokenizer


def _capture_one(model, tokenizer, text, modules):
    """Return final-two-token inputs and outputs for four actual linear modules."""
    import torch
    state, handles = {}, []
    for name,module in modules.items():
        def capture(_module, inputs, output, *, key=name):
            k = inputs[0][0, -2:, :].detach().float().cpu().clone()
            v = output[0, -2:, :].detach().float().cpu().clone()
            if k.shape[0] != 2 or v.shape[0] != 2:
                raise ValueError("Expected two distinct teacher-forced token slots")
            state[key] = (k, v)
        handles.append(module.register_forward_hook(capture))
    try:
        encoded = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        with torch.inference_mode():
            model(**encoded)
    finally:
        for handle in handles:
            handle.remove()
    if set(state) != set(modules):
        raise RuntimeError("Incomplete layer activation capture")
    return state


def _orthogonal_bases(ui_diffs, backend_diffs, rank=SUBSPACE_RANK):
    """SVD followed by modified Gram-Schmidt/QR for disjoint mode subspaces."""
    import torch
    a = torch.linalg.svd(ui_diffs, full_matrices=False).U[:, :rank]
    b_raw = torch.linalg.svd(backend_diffs, full_matrices=False).U[:, :rank]
    # Double-pass modified Gram-Schmidt removes both first-order and roundoff overlap.
    for _ in range(2):
        b_raw = b_raw - a @ (a.T @ b_raw)
    b = torch.linalg.qr(b_raw, mode="reduced").Q[:, :rank]
    if b.shape[1] != rank:
        raise ValueError("Not enough independent directions")
    cos = a.T @ b
    max_cross = float(cos.abs().max().item())
    if not math.isfinite(max_cross) or max_cross > 1e-5:
        raise RuntimeError(f"Orthogonality violated: max |cos|={max_cross}")
    return a.contiguous(), b.contiguous(), max_cross


def _rank32_update(weight, keys, diffs, basis, cap=CAP_FROBENIUS):
    """Ridge multi-key direct solve + an exactly rank<=32 SVD factorization."""
    import torch
    if keys.shape[1] != 50 or diffs.shape[1] != 50:
        raise ValueError("Required 25 clean trajectories x 2 teacher-forced positions")
    if weight.shape[0] != basis.shape[0] or weight.shape[1] != keys.shape[0]:
        raise ValueError("Invalid SVD/MLP linear dimensions")
    target_coefficients = basis.T @ diffs
    gram = keys.T @ keys
    ridge = max(float(torch.trace(gram).item()) / keys.shape[1], 1e-8) * 0.1
    inverse_keys = torch.linalg.solve(gram + ridge * torch.eye(50), keys.T)
    small = target_coefficients @ inverse_keys  # 32 x d_ff
    u, s, vh = torch.linalg.svd(small, full_matrices=False)
    left = basis @ (u[:, :SUBSPACE_RANK] * s[:SUBSPACE_RANK])
    right = vh[:SUBSPACE_RANK, :]
    delta = left @ right
    before = float(torch.linalg.vector_norm(diffs).item())
    w_norm = float(torch.linalg.vector_norm(weight).item())
    proposed = float(torch.linalg.vector_norm(delta).item())
    if min(before, w_norm, proposed) <= 0:
        raise RuntimeError("Degenerate direct edit")
    scale = min(1.0, 0.999 * cap * w_norm / proposed)
    left = (left * scale).contiguous()
    observed = float(torch.linalg.vector_norm(left @ right).item()) / w_norm
    if observed > cap + 1e-7 or not torch.isfinite(left).all() or not torch.isfinite(right).all():
        raise RuntimeError("Edit violated Frobenius/finite bound")
    return left, right.contiguous(), {"rank": SUBSPACE_RANK,
        "relative_frobenius": observed, "cap": cap, "ridge": ridge,
        "proposed_relative_frobenius": proposed / w_norm,
        "difference_norm": before}


def prepare_factors(model, tokenizer, sources):
    import torch
    from .weight_space import target_linear
    modules = {"layer8": target_linear(model, 8, "mlp.down_proj"),
               "layer16": target_linear(model, 16, "mlp.down_proj"),
               "layer12": target_linear(model, 12, "self_attn.o_proj"),
               "layer18": target_linear(model, 18, "self_attn.o_proj")}
    pairs = {name:{mode: {"keys":[],"diffs":[]} for mode in ("ui","backend")}
             for name in modules}
    for i,source in enumerate(sources):
        prompt = _capture_one(model, tokenizer, source["prompt"], modules)
        ref = _capture_one(model, tokenizer, source["reference"], modules)
        for name in modules:
            pairs[name][source["mode"]]["keys"].append(prompt[name][0].T)
            pairs[name][source["mode"]]["diffs"].append((ref[name][1] - prompt[name][1]).T)
        if (i+1) % 10 == 0:
            print(f"Teacher-forced source trajectories {i+1}/50", flush=True)

    tensors, metrics = {}, {}
    for name,module in modules.items():
        packed = {mode:{field: torch.cat(pairs[name][mode][field], dim=1).float()
                        for field in ("keys","diffs")}
                  for mode in ("ui","backend")}
        ui, backend, cross = _orthogonal_bases(packed["ui"]["diffs"], packed["backend"]["diffs"])
        tensors[f"{name}.ui_basis"] = ui
        tensors[f"{name}.backend_basis"] = backend
        # Correctly named: o_proj-output steering, not whole decoder residual.
        if name in ("layer12", "layer18"):
            for mode,base in (("ui",ui),("backend",backend)):
                tensors[f"{name}.{mode}_steering"] = base[:,0].contiguous()
        else:
            mode,base = ("ui",ui) if name == "layer8" else ("backend",backend)
            left,right,extra = _rank32_update(module.weight.detach().float().cpu(),
                packed[mode]["keys"],packed[mode]["diffs"],base)
            tensors[f"{name}.left"] = left
            tensors[f"{name}.right"] = right
            metrics[f"{name}.static_edit"] = extra
        metrics[f"{name}.subspace"] = {"max_abs_cross_cosine": cross,
                                        "ui_basis_rank": ui.shape[1],
                                        "backend_basis_rank": backend.shape[1],
                                        "unit_normalized": True}
    return tensors, metrics


def apply_static(model, factors):
    import torch
    from .weight_space import target_linear
    metrics = {}
    with torch.inference_mode():
        for layer in (8,16):
            module = target_linear(model,layer,"mlp.down_proj")
            left,right = factors[f"layer{layer}.left"],factors[f"layer{layer}.right"]
            delta = left @ right
            original = module.weight.detach().clone()
            if original.shape != delta.shape:
                raise ValueError("Factor shape mismatch")
            module.weight.add_(delta.to(module.weight.dtype))
            norm = float(torch.linalg.vector_norm((module.weight-original).float()).item() /
                         torch.linalg.vector_norm(original.float()).item())
            if norm > CAP_FROBENIUS+1e-6 or not torch.isfinite(module.weight).all():
                module.weight.copy_(original)
                raise RuntimeError("Applied static edit was invalid; restored weight")
            metrics[f"layer{layer}"] = norm
    return metrics


class RuntimeHooks:
    """Context-managed, generation-only token-triggered o_proj output steering."""

    def __init__(self, model, tokenizer, factors, alpha, mode):
        if alpha not in ALPHAS or mode not in ("ui","backend"):
            raise ValueError("Unexpected steering mode or multiplier")
        self.model,self.tokenizer,self.factors,self.alpha,self.mode = model,tokenizer,factors,alpha,mode
        self.handles,self.active,self.trigger_counts = [],None,Counter()
        self.decoded_tokens = {}

    def __enter__(self):
        import torch
        def prehook(_model, args, kwargs):
            ids = kwargs.get("input_ids")
            if ids is None and args:
                ids = args[0]
            if ids is None or ids.ndim != 2 or ids.shape[1] != 1:
                self.active = None  # Never steer prompt prefill.
                return
            flags = []
            for item in ids[:, -1].tolist():
                if item not in self.decoded_tokens:
                    self.decoded_tokens[item] = self.tokenizer.decode([item], skip_special_tokens=True)
                token = self.decoded_tokens[item]
                matches = [x for x in TRIGGER_KEYWORDS if re.search(r"\b"+x+r"\b", token)]
                flags.append(bool(matches))
                if matches:
                    self.trigger_counts[matches[0]] += 1
            self.active = torch.tensor(flags, dtype=torch.bool)
        self.handles.append(self.model.register_forward_pre_hook(prehook, with_kwargs=True))
        for layer in HOOK_LAYERS:
            vector = self.factors[f"layer{layer}.{self.mode}_steering"]
            if vector.shape != (896,):
                raise ValueError("Invalid hook vector size")
            def steer(_module, _input, output, *, direction=vector):
                if self.active is None or not self.active.any():
                    return output
                if not torch.is_tensor(output) or output.ndim != 3 or output.shape[-1] != 896:
                    raise RuntimeError("Unexpected o_proj hook output format")
                mask = self.active.to(output.device,dtype=output.dtype).view(-1,1,1)
                return output + (self.alpha * mask * direction.to(output.device,output.dtype).view(1,1,-1))
            self.handles.append(self.model.model.layers[layer].self_attn.o_proj.register_forward_hook(steer))
        return self

    def __exit__(self, exc_type, exc, tb):
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
        self.active = None


def generate(model, tokenizer, task_groups, factors, *, alpha=None, max_tokens=160, batch_size=4):
    import torch
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    out, trigger_counts = {},Counter()
    for mode, tasks in task_groups:
        for start in range(0,len(tasks),batch_size):
            batch = tasks[start:start+batch_size]
            encoded = tokenizer([task["prompt"] for task in batch], add_special_tokens=False,
                                return_tensors="pt", padding=True)
            hook = RuntimeHooks(model,tokenizer,factors,alpha,mode) if alpha is not None else None
            with torch.inference_mode():
                if hook:
                    with hook:
                        result = model.generate(**encoded,do_sample=False,
                                                max_new_tokens=max_tokens,
                                                pad_token_id=tokenizer.pad_token_id)
                    trigger_counts.update(hook.trigger_counts)
                else:
                    result = model.generate(**encoded,do_sample=False,
                                            max_new_tokens=max_tokens,
                                            pad_token_id=tokenizer.pad_token_id)
            completions = tokenizer.batch_decode(result[:,encoded["input_ids"].shape[1]:],skip_special_tokens=True)
            for task,completion in zip(batch,completions, strict=True):
                out[task["task_id"]] = completion
        print(f"CPU generated {len(tasks)} tasks for mode {mode}; alpha={alpha}",flush=True)
    return out, dict(trigger_counts)


def measure(records):
    count = len(records)
    if count == 0:
        raise ValueError("No verified task results")
    bins = Counter(r["failure_bin"] for r in records)
    if bins["passed"] != sum(bool(r["plus_pass"]) if "plus_pass" in r else bool(r["passed"]) for r in records):
        raise ValueError("Non-disjoint failure taxonomy")
    return {"count": count, "execution_passes": bins["passed"],
            "execution_pass_at_1": bins["passed"]/count,
            "syntax_valid": sum(bool(r["syntax_valid"]) for r in records),
            "syntax_validity": sum(bool(r["syntax_valid"]) for r in records)/count,
            "failure_bins": dict(bins),
            "passed_ids": [r["task_id"] for r in records if r["failure_bin"] == "passed"]}


def prepare(args):
    import torch
    from safetensors.torch import save_file
    from .rome20 import save_json
    from .sandbox_eval import require_sandbox
    require_sandbox()
    mbpp,web,sources,manifest = frozen_tasks()
    validate_references(sources,web)
    out = Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    save_json(out/"manifest.json",manifest)
    model,tokenizer = _torch_model()
    factor_tensors,diagnostics = prepare_factors(model,tokenizer,sources)
    if any(not torch.isfinite(v).all() for v in factor_tensors.values()):
        raise RuntimeError("Non-finite factors")
    save_file({k:v.detach().float().contiguous() for k,v in factor_tensors.items()},str(out/"factors.safetensors"),
              metadata={"model":MODEL_ID,"source_sha256":manifest["source_fixture_sha256"],
                        "task_manifest_sha256":manifest["manifest_sha256"]})
    factor_sha256 = hashlib.sha256((out/"factors.safetensors").read_bytes()).hexdigest()
    save_json(out/"diagnostics.json",{"model":MODEL_ID,"source_trajectories":50,
        "subspace_rank":SUBSPACE_RANK,"measured_cosine":diagnostics,
        "factor_sha256":factor_sha256,"manifest_sha256":manifest["manifest_sha256"],
        "training_steps":0,"reference_verification":"50/50 source and 50/50 web fixtures passed Docker tests"})
    print(json.dumps({"phase":"prepared","factors_sha256":factor_sha256,
                     "manifest_sha256":manifest["manifest_sha256"]}),flush=True)


def benchmark(args):
    import torch
    from safetensors.torch import load_file
    from .rome20 import save_json
    from .sandbox_eval import require_sandbox
    require_sandbox()
    if args.track not in TRACKS:
        raise ValueError("Unrecognized fixed benchmark track")
    mbpp,web,sources,manifest = frozen_tasks()
    prepared = json.loads((Path(args.prepared_dir)/"manifest.json").read_text(encoding="utf-8"))
    if prepared != manifest:
        raise ValueError("Benchmark dataset drift since factor capture")
    diag = json.loads((Path(args.prepared_dir)/"diagnostics.json").read_text(encoding="utf-8"))
    factor_path = Path(args.prepared_dir)/"factors.safetensors"
    sha = hashlib.sha256(factor_path.read_bytes()).hexdigest()
    if sha != diag["factor_sha256"] or diag["manifest_sha256"] != manifest["manifest_sha256"]:
        raise ValueError("Reversible factor provenance mismatch")
    factors = load_file(str(factor_path),device="cpu")
    model,tokenizer = _torch_model()
    n_params = sum(p.numel() for p in model.parameters())
    static = args.track.startswith("static") or args.track.startswith("hybrid")
    alpha = float(args.track.split("-")[-1]) if args.track.startswith(("dynamic-","hybrid-")) else None
    edits = apply_static(model,factors) if static else {}
    groups = [("backend",mbpp),("ui",web[:25]),("backend",web[25:])]
    outputs,triggers = generate(model,tokenizer,groups,factors,alpha=alpha,
                                max_tokens=args.max_new_tokens,batch_size=args.batch_size)
    del model
    gc.collect()
    mbpp_out = [outputs[p["task_id"]] for p in mbpp]
    web_out = [outputs[p["task_id"]] for p in web]
    out = Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    predictions = [{"task_id":p["task_id"],"mode":"python", "completion":outputs[p["task_id"]]}
                   for p in mbpp] + [{"task_id":p["task_id"],"mode":p["mode"],
                                      "completion":outputs[p["task_id"]]} for p in web]
    save_json(out/"predictions.json",predictions)
    python_results = docker_evaluate(mbpp,mbpp_out,web=False,workers=args.workers)
    web_results = docker_evaluate(web,web_out,web=True,workers=args.workers)
    records = [{**r,"mode":"python","execution_pass":r["plus_pass"]} for r in python_results] + [
        {**r,"mode":web[i]["mode"],"execution_pass":r["passed"]} for i,r in enumerate(web_results)]
    result = {"status":"completed","session":"014","track":args.track,"model":MODEL_ID,
              "parameter_count":n_params,"training_steps":0,"device":"cpu","threads":4,
              "decoding":{"greedy":True,"max_new_tokens":args.max_new_tokens,
                          "batch_size":args.batch_size},
              "alpha":alpha,"static_edits":edits,"trigger_counts":triggers,
              "factor_sha256":sha,"manifest":manifest,
              "mbpp_plus":measure(python_results),"custom_web":measure(web_results),
              "ui_react":measure(web_results[:25]),"backend_express":measure(web_results[25:]),
              "overall":measure(records),"task_results":records,
              "sandbox":"Restricted, unprivileged, network-disabled, read-only, CPU-capped Docker",
              "noted_limitations":"Custom web tasks are template-generated; mode labels are user-assigned. Hook trigger is token-decoded exact keyword, only in incremental decoding. Activation subspaces are correlative, not established semantics."}
    save_json(out/"report.json",result)
    print(json.dumps({"track":args.track,"overall":result["overall"],
                      "mbpp_plus":result["mbpp_plus"]["execution_passes"],
                      "web":result["custom_web"]["execution_passes"]}),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase",choices=("prepare","benchmark"),required=True)
    p.add_argument("--track",choices=TRACKS)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--prepared-dir",default="outputs/session014-prepared")
    p.add_argument("--max-new-tokens",type=int,default=160)
    p.add_argument("--batch-size",type=int,default=4)
    p.add_argument("--workers",type=int,default=2)
    args = p.parse_args()
    if args.phase == "prepare":
        if args.track is not None:
            p.error("--track is only valid for benchmark")
        prepare(args)
    else:
        if args.track is None:
            p.error("--track is mandatory for benchmark")
        benchmark(args)


if __name__ == "__main__":
    main()
