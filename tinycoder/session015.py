"""Session015: prompt-conditioned, gradient-free, rank32 low-rank MLP gating.

The factor file is an exact, hash-verified Session014 artifact. The pre-hooks
calculate low-rank matrix-vector products for each mode; the paired output
hooks add those products, implementing (W_base + gate*DeltaW) @ activations
WITHOUT changing the base weights. Model-generated code runs only in Docker.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gc
import hashlib
import json
from pathlib import Path
import re

from .session014 import (DOCKER_MBPP, DOCKER_WEB, MODEL_ID, _torch_model,
                        docker_evaluate, measure, select_mbpp, syntax_python)
from .session014_fixtures import make_web_tasks, sha256_json

EXPECTED_FACTOR_SHA256 = "1ad99ce6ebe432f637a42caaca2286bfbb032acaa0a3ff220f5dec163bfe7c8b"
EXCLUSION_FILE = Path("data/session015_excluded_mbpp_ids.json")
FACTOR_KEYS = ("layer8.left", "layer8.right", "layer16.left", "layer16.right")
TRACKS = ("baseline", "ungated", "gated-0.0", "gated-0.5", "gated-1.0", "gated-ui-only-1.0")
GATES = (0.0, 0.5, 1.0)
UI_TRIGGERS = ("import React", "<div", "useState", "useEffect", "className", "JSX")
BACKEND_TRIGGERS = ("express", "app.get", "app.post", "res.json", "async (req, res)")
MODEL_PARAMETER_COUNT = 494032768


def classify_prompt(prompt: str):
    """Only lexical evidence in the *prompt* determines mode; never task labels."""
    if not isinstance(prompt, str):
        raise TypeError("Expected original prompt text")
    ui = [x for x in UI_TRIGGERS if x in prompt]
    backend = [x for x in BACKEND_TRIGGERS if x in prompt]
    if ui and backend:
        return {"mode": "baseline", "matches": [*ui,*backend], "reason":"ambiguous"}
    if ui:
        return {"mode":"ui", "matches":ui, "reason":"ui_keyword"}
    if backend:
        return {"mode":"backend", "matches":backend, "reason":"api_keyword"}
    return {"mode":"baseline", "matches":[], "reason":"default_fallback"}


def task_fixtures():
    from evalplus.data import get_mbpp_plus, get_mbpp_plus_hash
    from evalplus.data.mbpp import get_mbpp
    from .rome20 import fetch_problems

    old=json.loads(EXCLUSION_FILE.read_text(encoding="utf-8"))
    excluded=set(old["session013_ids"] + old["session014_ids"])
    if (len(old["session013_ids"])!=100 or len(old["session014_ids"])!=50
            or len(excluded)!=150 or old["session014_factor_sha256"]!=EXPECTED_FACTOR_SHA256):
        raise ValueError("Historical task/factor provenance changed")
    selected=select_mbpp(get_mbpp_plus(),get_mbpp(),fetch_problems(),excluded,count=50)
    web=make_web_tasks(offset=25)
    if (len(web)!=50 or set(p["task_id"] for p in selected)&excluded or
            len(set(p["task_id"] for p in web))!=50):
        raise ValueError("Prior task reuse or incomplete fresh benchmark")

    detected={}
    for item in selected:
        gate=classify_prompt(item["prompt"])
        detected[item["task_id"]]=gate
        if gate["mode"]!="baseline":
            raise RuntimeError("Python prompt unexpectedly triggered a foreign-domain gate")
    for item in web:
        gate=classify_prompt(item["prompt"])
        detected[item["task_id"]]=gate
        if gate["mode"]!=item["mode"]:
            raise RuntimeError(f"Custom web task mode unrecognized: {item['task_id']} {gate}")
    manifest={
        "model":MODEL_ID,"sample_size":100,"mbpp_plus_count":50,
        "custom_ui_count":25,"custom_backend_count":25,
        "mbpp_plus_dataset_md5":get_mbpp_plus_hash(),
        "mbpp_task_ids":[p["task_id"] for p in selected],
        "web_task_ids":[p["task_id"] for p in web],
        "mbpp_prompt_hashes":{p["task_id"]:hashlib.sha256(p["prompt"].encode()).hexdigest()
                              for p in selected},
        "prior_mbpp_excluded":len(excluded),
        "prior_session014_web_task_ids":[f"WebUI/{i:02d}" for i in range(25)]+[
            f"WebAPI/{i:02d}" for i in range(25)],
        "web_fixture_sha256":sha256_json(web),
        "classifier_sha256":sha256_json({"ui":UI_TRIGGERS,"backend":BACKEND_TRIGGERS}),
        "pretraining_nonexposure_guaranteed":False,
        "web_test_provenance":"50 custom template-derived tasks with fresh identifiers and prompts, NOT official MBPP+",
        "source_factors_from_session":"014",
        "factor_sha256":EXPECTED_FACTOR_SHA256,
    }
    manifest["manifest_sha256"]=sha256_json(manifest)
    return selected,web,detected,manifest


def archived_factors(path: Path):
    import torch
    from safetensors.torch import load_file
    if hashlib.sha256(path.read_bytes()).hexdigest()!=EXPECTED_FACTOR_SHA256:
        raise ValueError("Session014 factor SHA-256 mismatch: refusing substituted edit")
    factors=load_file(str(path),device="cpu")
    if any(k not in factors for k in FACTOR_KEYS):
        raise ValueError("Required Layer8/Layer16 rank32 factors are missing")
    for layer in (8,16):
        left,right=factors[f"layer{layer}.left"],factors[f"layer{layer}.right"]
        if (left.shape!=(896,32) or right.ndim!=2 or right.shape[0]!=32
                or not torch.isfinite(left).all() or not torch.isfinite(right).all()):
            raise ValueError("Unexpected rank or nonfinite Session014 factor values")
    return factors


def track_configuration(name):
    if name not in TRACKS:
        raise ValueError("Unrecognized track")
    if name in ("baseline","ungated"):
        return {"name":name,"multiplier":None,"ui_only":False}
    return {"name":name,"multiplier":float(name.rsplit("-",1)[-1]),
            "ui_only":name.startswith("gated-ui-only")}


class ContextGatedFactors:
    """Exact low-rank functional weight edit via paired pre/output hooks.

    For a down_proj input X, forward pre-hook records M*X@R^T@L^T; forward
    output-hook adds it to W_base@X. At zero gate both hooks are no-ops.
    The modules' .weight tensors remain byte-for-byte untouched.
    """

    def __init__(self,model,factors,mode,multiplier,*,ui_only=False):
        if mode not in ("ui","backend","baseline") or multiplier not in GATES:
            raise ValueError("Invalid context gate")
        self.model,self.factors,self.mode,self.multiplier=model,factors,mode,multiplier
        self.ui_only=ui_only
        self.handles=[]
        self.pending={}
        self.prehook_calls=Counter()

    def scale_for(self,layer):
        if layer==8 and self.mode=="ui":
            return self.multiplier
        if layer==16 and self.mode=="backend" and not self.ui_only:
            return self.multiplier
        return 0.0

    def __enter__(self):
        import torch
        import torch.nn.functional as F
        for layer in (8,16):
            module=self.model.model.layers[layer].mlp.down_proj
            left=self.factors[f"layer{layer}.left"]
            right=self.factors[f"layer{layer}.right"]
            if module.weight.shape!=(left.shape[0],right.shape[1]):
                raise ValueError(f"Factor dimensions incompatible with Layer {layer}")
            strength=self.scale_for(layer)
            def prehook(_module, inputs, *, idx=layer, cap=strength, l=left, r=right):
                self.prehook_calls[f"layer{idx}"] += 1
                if cap:
                    x=inputs[0]
                    # Computation in the prehook means the masked weight product
                    # is ready before the original linear module is evaluated.
                    self.pending[idx]=cap*F.linear(
                        F.linear(x,r.to(device=x.device,dtype=x.dtype)),
                        l.to(device=x.device,dtype=x.dtype))
                return None  # The actual input tensor is intentionally unchanged.
            def posthook(_module,_inputs,output,*,idx=layer,cap=strength):
                if not cap:
                    return output
                extra=self.pending.pop(idx)
                if extra.shape!=output.shape:
                    raise RuntimeError("Masked projection output has wrong shape")
                return output+extra
            self.handles.append(module.register_forward_pre_hook(prehook))
            self.handles.append(module.register_forward_hook(posthook))
        return self

    def __exit__(self,exc_type,exc,tb):
        for h in self.handles:
            h.remove()
        self.handles.clear()
        self.pending.clear()


def generate_all(model,tokenizer,tasks,detected,factors,config,*,max_tokens=160,batch_size=4):
    import torch
    tokenizer.padding_side="left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token=tokenizer.eos_token
    outputs={}
    prehooks=Counter()
    for offset in range(0,len(tasks),batch_size):
        # Do not mix context modes in the same PyTorch generation call.
        part=tasks[offset:offset+batch_size]
        mode=detected[part[0]["task_id"]]["mode"]
        if any(detected[p["task_id"]]["mode"]!=mode for p in part):
            raise ValueError("Mixed generation context within a batch")
        encoded=tokenizer([p["prompt"] for p in part],return_tensors="pt",
                          padding=True,add_special_tokens=False)
        with torch.inference_mode():
            if config["multiplier"] is None:
                result=model.generate(**encoded,do_sample=False,max_new_tokens=max_tokens,
                                      pad_token_id=tokenizer.pad_token_id)
            else:
                with ContextGatedFactors(model,factors,mode,config["multiplier"],
                                         ui_only=config["ui_only"]) as gated:
                    result=model.generate(**encoded,do_sample=False,max_new_tokens=max_tokens,
                                          pad_token_id=tokenizer.pad_token_id)
                prehooks.update(gated.prehook_calls)
        answers=tokenizer.batch_decode(result[:,encoded["input_ids"].shape[1]:],
                                        skip_special_tokens=True)
        for task,answer in zip(part,answers,strict=True):
            outputs[task["task_id"]]=answer
    return outputs,dict(prehooks)


def run(args):
    import torch
    from .rome20 import save_json
    from .session014 import apply_static
    from .sandbox_eval import require_sandbox
    require_sandbox()
    config=track_configuration(args.track)
    if args.batch_size!=4 or args.max_new_tokens!=160 or args.workers!=2:
        raise ValueError("Frozen 160-token, batch4, Docker2 benchmark protocol required")
    mbpp,web,detected,manifest=task_fixtures()
    factors=archived_factors(Path(args.factor_path))
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing measured benchmark")
    out.mkdir(parents=True,exist_ok=True)
    save_json(out/"manifest.json",manifest)

    model,tokenizer=_torch_model()
    if sum(p.numel() for p in model.parameters())!=MODEL_PARAMETER_COUNT:
        raise ValueError("Qwen parameter scale changed")
    static_changes=apply_static(model,factors) if args.track=="ungated" else {}
    before_weights={layer: model.model.layers[layer].mlp.down_proj.weight.detach().clone()
                    for layer in (8,16)}
    all_tasks=mbpp+web
    # Contexts are naturally homogeneous in these three explicit slices.
    batches=(mbpp,web[:25],web[25:])
    outputs,hook_calls={},Counter()
    for group in batches:
        generated,calls=generate_all(model,tokenizer,group,detected,factors,config,
                                     max_tokens=args.max_new_tokens,batch_size=args.batch_size)
        outputs.update(generated)
        hook_calls.update(calls)
        print(f"CPU generation complete: {len(outputs)}/100, track={args.track}",flush=True)
    for layer in (8,16):
        if not torch.equal(before_weights[layer],model.model.layers[layer].mlp.down_proj.weight):
            raise RuntimeError("Runtime hook mutated the actual pretrained weight matrix")
    del model
    gc.collect()
    mbpp_completions=[outputs[p["task_id"]] for p in mbpp]
    web_completions=[outputs[p["task_id"]] for p in web]
    predictions=[{"task_id":p["task_id"],"completion":outputs[p["task_id"]],
                  "detected_mode":detected[p["task_id"]]["mode"],
                  "keywords":detected[p["task_id"]]["matches"]}
                 for p in all_tasks]
    save_json(out/"predictions.json",predictions)
    python_results=docker_evaluate(mbpp,mbpp_completions,web=False,workers=args.workers)
    web_results=docker_evaluate(web,web_completions,web=True,workers=args.workers)
    records=[{**x,"execution_pass":x["plus_pass"],"mode":"python"} for x in python_results]+[
        {**x,"execution_pass":x["passed"],"mode":web[i]["mode"]}
        for i,x in enumerate(web_results)]
    report={"status":"completed","session":"015","track":args.track,
            "model":MODEL_ID,"parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
            "factor_sha256":EXPECTED_FACTOR_SHA256,"manifest":manifest,
            "mode_detector":{k:detected[k] for k in manifest["mbpp_task_ids"]+manifest["web_task_ids"]},
            "configuration":config,"static_relative_norms":static_changes,
            "forward_prehook_calls":dict(hook_calls),
            "baseline_weights_unchanged_by_hooks":True,
            "mbpp_plus":measure(python_results),
            "react_ui":measure(web_results[:25]),
            "express_backend":measure(web_results[25:]),
            "web_combined":measure(web_results),"overall":measure(records),
            "task_results":records,
            "docker":"Network-disabled/read-only/unprivileged Docker; EvalPlus 0.3.1 MBPP+ and custom React/Express assertions",
            "interpretation_limits":"Custom web tasks are template variants. No guarantee against foundation-model pretraining exposure. Python/Express preservation is measured against the concurrent baseline on the same fresh tasks, not by copying Session014's old scores."}
    save_json(out/"report.json",report)
    print(json.dumps({"track":args.track,"mbpp":report["mbpp_plus"]["execution_passes"],
                      "ui":report["react_ui"]["execution_passes"],
                      "api":report["express_backend"]["execution_passes"],
                      "total":report["overall"]["execution_passes"]}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--track",choices=TRACKS,required=True)
    p.add_argument("--factor-path",type=Path,default=Path("outputs/session014-prepared/factors.safetensors"))
    p.add_argument("--output-dir",required=True)
    p.add_argument("--max-new-tokens",type=int,default=160)
    p.add_argument("--batch-size",type=int,default=4)
    p.add_argument("--workers",type=int,default=2)
    run(p.parse_args())


if __name__=="__main__":
    main()
