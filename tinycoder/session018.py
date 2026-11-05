"""Session018 extreme but bounded Qwen0.5B Python semantic search.

Freezes Session017b's trusted UI scaffold and Express code byte-for-byte.
Derives public distinguishing probes, applies optional type-directed AST
repairs, samples up to eight Python continuations and two feedback repairs.
All generated programs execute ONLY in restricted network-disabled Docker.
Holdout values are loaded after ALL candidate selection has finished.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gc
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import _torch_model, MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session017 import check_apps, metrics
from .session017_contracts import contract_sha256, contracts, holdout_cases, module_prompt
from .session018_probes import augmented_public, typed_ast_repair


ARCHIVED = Path("experiments/session017_scaffold_predictions.json")
PREVIOUS = Path("experiments/session017_scaffold_report.json")
PYTHON_IMAGE = "tinycoder-session018-python:1"
NEW_TOKENS = 220
SAMPLE_DRAWS = 8
REPAIR_ROUNDS = 2


def failure(task_id, reason):
    return {"task_id":task_id,"syntax_valid":False,"passed_count":0,
            "passed_all":False,"cases_total":4,
            "failures":[{"index":-1,"error":reason}]}


def docker_python(task, code, cases, *, timeout=18):
    """Evaluate a candidate with independent, per-input Python fork timeouts."""
    with tempfile.TemporaryDirectory(prefix="session018_") as directory:
        root = Path(directory)
        src,dst = root/"in",root/"out"
        src.mkdir(mode=0o755)
        dst.mkdir(mode=0o777)
        os.chmod(root,0o755)
        os.chmod(dst,0o777)
        inp=src/"input.json"
        inp.write_text(json.dumps({"task_id":task["task_id"],
                                   "source":code,"cases":cases}),encoding="utf-8")
        os.chmod(inp,0o644)
        name="tinycoder-s018-"+uuid.uuid4().hex[:14]
        cmd=["docker","run","--rm","--name",name,"--network","none",
             "--read-only","--cap-drop","ALL","--security-opt","no-new-privileges",
             "--pids-limit","64","--memory","512m","--cpus","1",
             "--user","65534:65534","--tmpfs","/tmp:rw,nosuid,size=64m",
             "--mount",f"type=bind,src={src.resolve()},dst=/work,readonly",
             "--mount",f"type=bind,src={dst.resolve()},dst=/results",
             PYTHON_IMAGE,"/work/input.json","/results/result.json"]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker","rm","-f",name],capture_output=True,
                           text=True,timeout=10,check=False)
            return failure(task["task_id"],f"Isolated Python Docker timeout ({timeout}s)")
        if p.returncode or not (dst/"result.json").exists():
            return failure(task["task_id"],"Docker Python verifier error: "+p.stderr[-200:])
        result=json.loads((dst/"result.json").read_text(encoding="utf-8"))
        if result["task_id"] != task["task_id"] or result["cases_total"] != len(cases):
            raise RuntimeError("Python verifier altered task or case identity")
        return result


def python_checks(tasks, solutions, probes, *,workers=4):
    require_sandbox()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda t: docker_python(t,solutions[t["task_id"]]["logic"],
                                                    probes[t["task_id"]]),tasks))


def priority(record, source):
    return (int(record["passed_count"]),bool(record["syntax_valid"]),-len(source))


def sample(model,tokenizer,tasks,prompts,*,seed,temperature,batch_size=4):
    import torch
    if not tasks:
        return {},0
    torch.manual_seed(seed)
    tokenizer.padding_side="left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token=tokenizer.eos_token
    answer={}
    tokens=0
    for start in range(0,len(tasks),batch_size):
        batch=tasks[start:start+batch_size]
        text=[prompts[t["task_id"]] for t in batch]
        encoded=tokenizer(text,padding=True,return_tensors="pt",add_special_tokens=False)
        with torch.inference_mode():
            ids=model.generate(**encoded,do_sample=True,temperature=temperature,
                               top_p=0.95,max_new_tokens=NEW_TOKENS,
                               pad_token_id=tokenizer.pad_token_id)
        delta=ids[:,encoded["input_ids"].shape[1]:]
        continuation=tokenizer.batch_decode(delta,skip_special_tokens=True)
        for task,value in zip(batch,continuation,strict=True):
            answer[task["task_id"]]=value
        tokens+=sum(int((row!=tokenizer.pad_token_id).sum().item()) for row in delta)
    return answer,tokens


def repair_prompt(task,code,diagnostic,public_cases):
    """Feedback is limited to additional authored PUBLIC probe examples."""
    failed=diagnostic["failures"]
    index=failed[0]["index"] if failed else 0
    if index<0 or index>=len(public_cases):
        index=0
    example=public_cases[index]
    reason=(failed[0]["error"] if failed else "Did not satisfy public tests")[:250]
    previous="\n".join("# "+line for line in code.splitlines()[-24:])
    return ("# Repair this Python implementation using the failing PUBLIC example.\n"
            f"# Input: {json.dumps(example['payload'],sort_keys=True)}\n"
            f"# Expected: {json.dumps(example['expected'],sort_keys=True)}\n"
            f"# Failure: {reason.replace(chr(10),' ')}\n"
            f"# Previous attempt:\n{previous}\n"
            "# Rewrite the function below correctly, output code only.\n"
            + module_prompt(task,"logic"))


def evaluate_candidate(task,source,cases,*,label,history):
    observed=docker_python(task,source,cases)
    # Test a generic AST-normalized variant too, without source rewriting
    # tailored to a particular task answer or hidden test.
    normalized,rewrites=typed_ast_repair(source,task)
    options=[(source,observed,label,0)]
    if rewrites and normalized!=source:
        checked=docker_python(task,normalized,cases)
        options.append((normalized,checked,label+"-typed",rewrites))
    for code,result,variant,fixes in options:
        history.append({"source":variant,"public_result":result,
                        "typed_rewrites":fixes,"code":code})
    return max(options,key=lambda x:priority(x[1],x[0]))


def run(args):
    require_sandbox()
    if args.batch_size!=4 or args.workers!=4:
        raise ValueError("Session018 frozen CPU protocol")
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing overwrite of existing Session018 outputs")
    out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    tasks=contracts()
    task_by_id={t["task_id"]:t for t in tasks}
    allids=[t["task_id"] for t in tasks]
    public={t["task_id"]:augmented_public(t) for t in tasks}
    archived=json.loads(ARCHIVED.read_text(encoding="utf-8"))
    control=archived["guided_scaffold"]
    if set(control)!=set(allids):
        raise ValueError("Frozen scaffold branch does not contain ten tasks")
    if any(set(control[tid])!={"logic","api","ui"} for tid in allids):
        raise ValueError("Incomplete original source bundle")
    # Only frozen generated Python logic may change. React/Express stay byte exact.
    current={tid:dict(control[tid]) for tid in allids}
    history={tid:[] for tid in allids}
    states={r["task_id"]:r for r in python_checks(tasks,current,public)}
    for tid in allids:
        history[tid].append({"source":"session017b-frozen-control",
                             "public_result":states[tid],"typed_rewrites":0,
                             "code":current[tid]["logic"]})

    # Track 1: generic AST repair based on public input dictionaries only.
    for task in tasks:
        tid=task["task_id"]
        normalized,count=typed_ast_repair(current[tid]["logic"],task)
        if count:
            candidate=docker_python(task,normalized,public[tid])
            history[tid].append({"source":"typed-ast","public_result":candidate,
                                 "typed_rewrites":count,"code":normalized})
            if priority(candidate,normalized)>priority(states[tid],current[tid]["logic"]):
                current[tid]["logic"]=normalized
                states[tid]=candidate
    typed={tid:dict(current[tid]) for tid in allids}
    save_json(out/"typed_checkpoint.json",{"results":states,
                                             "accepted":{tid:current[tid]["logic"]!=control[tid]["logic"]
                                                         for tid in allids}})
    print(f"Typed-parse public 4/4: {sum(s['passed_all'] for s in states.values())}/10",flush=True)

    model,tokenizer=_torch_model()
    if sum(p.numel() for p in model.parameters())!=MODEL_PARAMETER_COUNT:
        raise RuntimeError("Not frozen Qwen2.5-Coder-0.5B base")
    sampled_tokens=0
    repair_tokens=0
    draw_active={}
    search4=None
    for draw in range(1,SAMPLE_DRAWS+1):
        unresolved=[t for t in tasks if not states[t["task_id"]]["passed_all"]]
        draw_active[str(draw)]=len(unresolved)
        if unresolved:
            prompts={t["task_id"]:module_prompt(t,"logic") for t in unresolved}
            generated,tokens=sample(model,tokenizer,unresolved,prompts,
                                    seed=2026111800+draw,
                                    temperature=0.65 if draw%2 else 0.95)
            sampled_tokens+=tokens
            # CPU-only public tests run serially per candidate to preserve
            # the exact candidate ordering and reproducible acceptance.
            for task in unresolved:
                tid=task["task_id"]
                code=prompts[tid]+generated[tid]
                proposal,assessed,_,_=evaluate_candidate(
                    task,code,public[tid],label=f"draw-{draw}",history=history[tid])
                if priority(assessed,proposal)>priority(states[tid],current[tid]["logic"]):
                    current[tid]["logic"]=proposal
                    states[tid]=assessed
        save_json(out/f"checkpoint-draw{draw:02d}.json",{
            "public":states,"active":len(unresolved),"tokens":sampled_tokens})
        if draw==4:
            search4={tid:dict(current[tid]) for tid in allids}
    assert search4 is not None

    for round_idx in range(1,REPAIR_ROUNDS+1):
        unresolved=[t for t in tasks if not states[t["task_id"]]["passed_all"]]
        if not unresolved:
            break
        prompts={t["task_id"]:repair_prompt(
            t,current[t["task_id"]]["logic"],states[t["task_id"]],public[t["task_id"]])
                 for t in unresolved}
        generated,tokens=sample(model,tokenizer,unresolved,prompts,
                                seed=2026111900+round_idx,temperature=0.65)
        repair_tokens+=tokens
        for task in unresolved:
            tid=task["task_id"]
            code=module_prompt(task,"logic")+generated[tid]
            proposal,assessed,_,_=evaluate_candidate(
                task,code,public[tid],label=f"repair-{round_idx}",history=history[tid])
            if priority(assessed,proposal)>priority(states[tid],current[tid]["logic"]):
                current[tid]["logic"]=proposal
                states[tid]=assessed
        save_json(out/f"checkpoint-repair{round_idx}.json",{
            "public":states,"tokens":repair_tokens})
    del model
    gc.collect()
    extreme={tid:dict(current[tid]) for tid in allids}
    save_json(out/"predictions.json",{
        "control":control,"typed_ast":typed,"search4":search4,"search8_repair2":extreme})
    save_json(out/"candidate_public_archive.json",history)

    # STRICT SEPARATION: Only now load the independent holdout values.
    hidden=holdout_cases()
    results={}
    for name,solutions in (("control",control),("typed_ast",typed),
                           ("search4",search4),("search8_repair2",extreme)):
        observed=check_apps(tasks,solutions,hidden)
        results[name]={"holdout":metrics(observed),"task_results":observed}

    previous=json.loads(PREVIOUS.read_text(encoding="utf-8"))
    if (previous.get("status")!="completed"
        or previous.get("model")!=MODEL_ID
        or previous.get("manifest_sha256")!=contract_sha256(tasks)
        or results["control"]["holdout"]!=previous["guided_scaffold"]):
        raise ValueError("Session017b original five-app control did not reproduce")
    for track in ("typed_ast","search4","search8_repair2"):
        sources={"typed_ast":typed,"search4":search4,
                 "search8_repair2":extreme}[track]
        if any(sources[tid][role]!=control[tid][role]
               for tid in allids for role in ("api","ui")):
            raise RuntimeError("Frozen React/Express source was modified")
    public_passes=sum(bool(states[tid]["passed_all"]) for tid in allids)
    report={
        "status":"completed","session":"018","branch":"exp/16-extreme-python-search",
        "model":MODEL_ID,"parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
        "source":"Frozen Session017b guided_scaffold source, exact full-app holdout control reproduced",
        "manifest_sha256":contract_sha256(tasks),"task_ids":allids,
        "tracks":results,"selection":{
            "public_original_cases_per_app":2,"extra_public_distinguishing_probes_per_app":2,
            "holdout_cases_per_app":2,"public_passes_after_search":public_passes,
            "holdout_used_during_selection":False,"react_express_source_unchanged":True,
            "sampled_task_count_by_draw":draw_active,
            "typed_repairs_from_known_dictionary_fields":True},
        "compute":{"sample_draws_max":SAMPLE_DRAWS,"repair_rounds_max":REPAIR_ROUNDS,
                   "new_output_tokens":sampled_tokens+repair_tokens,
                   "sample_output_tokens":sampled_tokens,"repair_output_tokens":repair_tokens,
                   "wall_seconds":round(time.monotonic()-start,2)},
        "candidate_archive":"experiments/session018_extreme_public_candidates.json",
        "predictions":"experiments/session018_extreme_predictions.json",
        "caveats":"These are ten custom authored vertical slices with explicit schemas, not real production projects. Selection uses original public examples AND two additional authored public contract probes; hidden values are withheld until final execution scoring. Extra inference and typed AST compiler repairs are system capabilities, NOT an improvement to the 0.5B model's intrinsic weights or single-sample pass@1. No JS/React or Express modifications are included in this track."
    }
    save_json(out/"report.json",report)
    print(json.dumps({"full_apps":{name:score["holdout"]["full_app_passes"]
                                     for name,score in results.items()},
                      "new_output_tokens":sampled_tokens+repair_tokens}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",default="outputs/session018")
    parser.add_argument("--batch-size",type=int,default=4)
    parser.add_argument("--workers",type=int,default=4)
    run(parser.parse_args())


if __name__=="__main__":
    main()
