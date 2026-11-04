"""Session016: adaptive execution-guided candidate search on frozen Qwen0.5B.

This is *system-level* test-time search, never parameter training or editing.
Selection sees original MBPP public test_list and newly generated web smoke
tests only; the EvalPlus expanded oracle is inaccessible until final scoring.
All generated programs are executed exclusively in restricted Docker.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gc
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import tempfile
import time
import uuid

from .session014 import (_torch_model, docker_command, docker_evaluate, measure,
                        DOCKER_MBPP, DOCKER_WEB, MODEL_ID)
from .session015 import MODEL_PARAMETER_COUNT, task_fixtures
from .rome20 import save_json
from .sandbox_eval import require_sandbox

TRACKS = ("search2", "search4")
BASELINE_PREDICTIONS = Path("experiments/session015_gated_predictions.json")
MAX_NEW_TOKENS = 160


def original_public_tests(mbpp):
    from evalplus.data.mbpp import get_mbpp
    original = get_mbpp()
    public = {}
    for problem in mbpp:
        task_id = problem["task_id"]
        key = task_id.rsplit("/",1)[1]
        tests = original[key].get("test_list", [])
        if not isinstance(tests, list) or not tests:
            raise ValueError(f"No public MBPP tests for {task_id}")
        public[task_id] = tests
    return public


def alternate_web_tests(task):
    """Task-spec-derived smoke inputs; no hidden benchmark result is read."""
    n = int(task["task_id"].split("/")[-1])
    route = f"/endpoint-{n:02d}"
    family = task["family"]
    if task["mode"] == "ui":
        if family == 0:
            return [{"props":{"value":"probe-value"},"contains":[f'data-testid="w{n}"',"probe-value"]}]
        if family == 1:
            return [{"props":{"text":"probe"},"contains":[f"{n}:PROBE","<h2>"]}]
        if family == 2:
            return [{"props":{"items":["probe","item"]},"contains":["<ul>","<li>probe</li>","<li>item</li>"]}]
        if family == 3:
            return [{"props":{"disabled":True},"contains":["<button",f"Action {n}","disabled"]}]
        return [{"props":{"ready":False},"contains":[f"WAIT {n}","<section>"],
                 "not_contains":[f"READY {n}"]}]
    if family == 0:
        return [{"method":"get","path":route,"body":None,"expected":{"message":f"hello-{n}"}}]
    if family == 1:
        return [{"method":"post","path":route,"body":{"a":12,"b":-9},
                 "expected":{"sum":n+3}}]
    if family == 2:
        return [{"method":"get","path":f"{route}/43","body":None,
                 "expected":{"id":43,"tag":f"id-{n}"}}]
    if family == 3:
        return [{"method":"get","path":f"{route}?q=probe","body":None,
                 "expected":{"q":"probe","length":5}}]
    return [{"method":"get","path":route,"body":None,
             "expected":{"ok":True,"version":n}}]


def _public_python_chunk(items,index):
    with tempfile.TemporaryDirectory(prefix="session016_public_") as directory:
        root=Path(directory)
        inp,out=root/"in",root/"out"
        inp.mkdir(mode=0o755)
        out.mkdir(mode=0o777)
        os.chmod(root,0o755)
        os.chmod(out,0o777)
        data=inp/"input.pkl"
        data.write_bytes(pickle.dumps(items,protocol=4))
        worker=inp/"worker.py"
        shutil.copyfile(Path(__file__).with_name("session016_public_mbpp_worker.py"),worker)
        os.chmod(data,0o644)
        os.chmod(worker,0o644)
        name="tinycoder-s016-"+uuid.uuid4().hex[:16]
        cmd=docker_command(DOCKER_MBPP,inp,out,name,False)
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=160)
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker","rm","-f",name],capture_output=True,check=False)
            raise RuntimeError(f"Public-check Docker timed out: chunk {index}") from exc
        if proc.returncode:
            raise RuntimeError(f"Public-check Docker failed: {proc.stderr[-1000:]}")
        result=json.loads((out/"result.json").read_text())
        if [x["task_id"] for x in result] != [x["task_id"] for x in items]:
            raise RuntimeError("Public Docker result IDs changed")
        return result


def _isolated_web_one(task, completion, *, timeout=18):
    """Each generated JS program gets its OWN bounded Docker lifetime.

    React server rendering and synchronous Express handlers can hang the
    Node event loop; framework request timeouts cannot interrupt a CPU loop.
    Never allow one bad candidate to terminate the whole benchmark chunk.
    """
    with tempfile.TemporaryDirectory(prefix="session016_web_") as directory:
        root=Path(directory)
        inp,out=root/"in",root/"out"
        inp.mkdir(mode=0o755)
        out.mkdir(mode=0o777)
        os.chmod(root,0o755)
        os.chmod(out,0o777)
        data=inp/"input.json"
        data.write_text(json.dumps([{"task_id":task["task_id"],"task":task,
                                     "solution":task["prompt"]+completion}]),encoding="utf-8")
        os.chmod(data,0o644)
        name="tinycoder-s016-web-"+uuid.uuid4().hex[:12]
        cmd=docker_command(DOCKER_WEB,inp,out,name,True)
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker","rm","-f",name],capture_output=True,
                           text=True,timeout=10,check=False)
            return {"task_id":task["task_id"],"syntax_valid":False,"passed":False,
                    "failure_bin":"unclassified_logic_gap",
                    "error":f"timeout after {timeout}s (syntax unknown)"}
        if proc.returncode or not (out/"result.json").exists():
            return {"task_id":task["task_id"],"syntax_valid":False,"passed":False,
                    "failure_bin":"unclassified_logic_gap",
                    "error":f"isolated Docker error: {proc.stderr[-240:]}"}
        result=json.loads((out/"result.json").read_text(encoding="utf-8"))
        if len(result)!=1 or result[0]["task_id"]!=task["task_id"]:
            raise RuntimeError("Isolated JS evaluator changed task identity")
        return result[0]


def safe_web_evaluate(tasks,completions,*,workers=4):
    """Score potentially nonterminating JS without access to the host runtime."""
    require_sandbox()
    if len(tasks)!=len(completions):
        raise ValueError("Mismatched custom web evaluation")
    if not tasks:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda x:_isolated_web_one(x[0],x[1]),
                             zip(tasks,completions,strict=True)))


def check_public(tasks,completions,public_tests,*,workers=2):
    """No EvalPlus private oracle, canonical solution, or plus-input is loaded."""
    require_sandbox()
    if len(tasks)!=len(completions):
        raise ValueError("Public task/completion mismatch")
    if not tasks:
        return []
    if tasks[0]["task_id"].startswith("Mbpp/"):
        entries=[{"task_id":task["task_id"],"solution":task["prompt"]+completion,
                  "public_tests":public_tests[task["task_id"]]}
                 for task,completion in zip(tasks,completions,strict=True)]
        chunks=[entries[i:i+5] for i in range(0,len(entries),5)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts=list(pool.map(lambda x:_public_python_chunk(x[1],x[0]),enumerate(chunks)))
        return [x for batch in parts for x in batch]
    smoke=[{**task,"tests":alternate_web_tests(task)} for task in tasks]
    return safe_web_evaluate(smoke,completions,workers=4)


def sample(model,tokenizer,tasks,*,seed,prompts=None,batch_size=4):
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
        inputs=[prompts[t["task_id"]] if prompts else t["prompt"] for t in batch]
        encoded=tokenizer(inputs,padding=True,return_tensors="pt",add_special_tokens=False)
        with torch.inference_mode():
            sequence=model.generate(**encoded,do_sample=True,temperature=0.7,
                                    top_p=1.0,max_new_tokens=MAX_NEW_TOKENS,
                                    pad_token_id=tokenizer.pad_token_id)
        result=sequence[:,encoded["input_ids"].shape[1]:]
        output=tokenizer.batch_decode(result,skip_special_tokens=True)
        for task,completion in zip(batch,output,strict=True):
            answer[task["task_id"]]=completion
        tokens+=sum(int((row!=tokenizer.pad_token_id).sum().item()) for row in result)
    return answer,tokens


def _groups(tasks):
    return [tasks[:50],tasks[50:75],tasks[75:]]


def make_repair_prompt(task,old_completion,diagnostic):
    """Prompt-only repair; never evaluates candidate code on the host."""
    reason=str(diagnostic.get("error") or diagnostic.get("failure_bin") or "Failed checks")
    reason=reason.replace("\n"," ")[:180]
    previous=old_completion[:1300]
    if task["task_id"].startswith("Mbpp/"):
        commented="\n".join("# "+line for line in previous.splitlines()[:28])
        return (f"# Previous solution failed public checks: {reason}\n"
                f"# Previous attempt:\n{commented}\n"
                f"# Write the corrected implementation below.\n{task['prompt']}")
    return (f"/* Previous implementation failed a public smoke test: {reason}\n"
            f"{previous}\n*/\n// Corrected implementation:\n{task['prompt']}")


def candidate_priority(item):
    result=item.get("public_result",{})
    return (bool(result.get("passed")),
            bool(result.get("syntax_valid")),
            result.get("failure_bin")=="assertion_error",
            -len(item["completion"]))


def best(candidates):
    return max(candidates,key=candidate_priority)


def _evaluate_new(task_groups,completions,public_tests,candidates,stage):
    for group in task_groups:
        if not group:
            continue
        results=check_public(group,[completions[t["task_id"]] for t in group],public_tests)
        for task,result in zip(group,results,strict=True):
            candidates[task["task_id"]].append({
                "source":stage,"completion":completions[task["task_id"]],
                "public_result":result})


def run(args):
    require_sandbox()
    if args.track not in TRACKS or args.batch_size!=4 or args.workers!=2:
        raise ValueError("Frozen Session016 protocol")
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing evaluation")
    out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    mbpp,web,detected,manifest=task_fixtures()
    tasks=mbpp+web
    old=json.loads(BASELINE_PREDICTIONS.read_text(encoding="utf-8"))
    baseline=old["baseline"]
    if [p["task_id"] for p in baseline] != [p["task_id"] for p in tasks]:
        raise ValueError("Published Session015 control IDs differ from frozen tasks")
    public=original_public_tests(mbpp)
    # Never look up canonical solutions or EvalPlus expanded tests for selection.
    candidates={t["task_id"]:[] for t in tasks}
    baseline_map={p["task_id"]:p["completion"] for p in baseline}
    _evaluate_new(_groups(tasks),baseline_map,public,candidates,"session015-greedy-control")
    print("Verified public checks on frozen baseline completions",flush=True)

    model,tokenizer=_torch_model()
    if sum(p.numel() for p in model.parameters())!=MODEL_PARAMETER_COUNT:
        raise RuntimeError("Model parameter scale changed")
    generated_tokens=0
    # One new independent sample for every task, preserving the original
    # greedy output as candidate zero.
    for group in _groups(tasks):
        generated,tokens=sample(model,tokenizer,group,seed=20261116)
        generated_tokens+=tokens
        save_json(out/f"sample1-{group[0]['task_id'].split('/')[0]}.json",generated)
        _evaluate_new([group],generated,public,candidates,"sample-1")
    print("Stage 1: two candidates per task scored on public checks",flush=True)

    # Adaptive budget: expand to four only when BOTH initial candidates fail.
    if args.track=="search4":
        unresolved=[t for t in tasks if not best(candidates[t["task_id"]])["public_result"]["passed"]]
        expanded_count=len(unresolved)
        for draw in (2,3):
            for mode in ("Mbpp/","WebUI/","WebAPI/"):
                group=[t for t in unresolved if t["task_id"].startswith(mode)]
                generated,tokens=sample(model,tokenizer,group,seed=20261116+draw)
                generated_tokens+=tokens
                save_json(out/f"sample{draw}-{mode.rstrip('/')}.json",generated)
                _evaluate_new([group],generated,public,candidates,f"sample-{draw}")
            unresolved=[t for t in unresolved
                        if not best(candidates[t["task_id"]])["public_result"]["passed"]]
        print(f"Stage 2: adaptively expanded {expanded_count} tasks (stopping when solved)",flush=True)

    # Exactly one prompted repair for still unresolved tasks.
    unresolved=[t for t in tasks if not best(candidates[t["task_id"]])["public_result"]["passed"]]
    for mode in ("Mbpp/","WebUI/","WebAPI/"):
        group=[t for t in unresolved if t["task_id"].startswith(mode)]
        prompts={}
        for task in group:
            chosen=best(candidates[task["task_id"]])
            prompts[task["task_id"]]=make_repair_prompt(
                task,chosen["completion"],chosen["public_result"])
        generated,tokens=sample(model,tokenizer,group,seed=20261119,prompts=prompts)
        generated_tokens+=tokens
        save_json(out/f"repair-{mode.rstrip('/')}.json",generated)
        _evaluate_new([group],generated,public,candidates,"feedback-repair")
    print(f"Stage 3: attempted feedback repair for {len(unresolved)} tasks",flush=True)
    del model
    gc.collect()

    winners={t["task_id"]:best(candidates[t["task_id"]]) for t in tasks}
    outputs=[winners[t["task_id"]]["completion"] for t in tasks]
    save_json(out/"predictions.json",[
        {"task_id":t["task_id"],"completion":winners[t["task_id"]]["completion"],
         "winning_source":winners[t["task_id"]]["source"],
         "public_pass":winners[t["task_id"]]["public_result"]["passed"]}
        for t in tasks])
    # This is the FIRST point at which expanded/private EvalPlus tests run.
    python=docker_evaluate(mbpp,outputs[:50],web=False,workers=args.workers)
    js=safe_web_evaluate(web,outputs[50:],workers=4)
    full=[{**r,"mode":"python"} for r in python]+[
        {**r,"mode":web[i]["mode"]} for i,r in enumerate(js)]
    counts=Counter(winners[t["task_id"]]["source"] for t in tasks)
    public_passes=sum(bool(winners[t["task_id"]]["public_result"]["passed"]) for t in tasks)
    report={
        "status":"completed","session":"016","track":args.track,
        "model":MODEL_ID,"parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
        "baseline_source":"Session015 stored untouched greedy predictions; no new baseline inference",
        "manifest":manifest,"generation":{"temperature":0.7,"max_new_tokens":160,
            "initial_candidates_per_task":2,"max_candidates_before_repair":
            (4 if args.track=="search4" else 2),"max_repair_rounds":1,
            "generated_output_tokens":generated_tokens,
            "wall_seconds":round(time.monotonic()-started,2)},
        "selection":{"public_passes":public_passes,"winning_source_counts":dict(counts),
                     "public_python_source":"Original MBPP test_list only",
                     "public_web_source":"Spec-derived smoke cases; some constant/boolean cases necessarily overlap official custom fixture checks",
                     "plus_test_leakage":False},
        "mbpp_plus":measure(python),"react_ui":measure(js[:25]),
        "express_backend":measure(js[25:]),"overall":measure(full),
        "task_results":full,
        "candidate_records":[{"task_id":task["task_id"],"candidates":candidates[task["task_id"]]}
                              for task in tasks],
        "caveats":"Final expanded MBPP+ tests were not visible during selection. Custom web tests are authored template checks and not independent unseen third-party tests; some public smoke tests necessarily overlap semantically. System-level pass@1 includes additional inference, so report tokens and wall-time separately."
    }
    save_json(out/"report.json",report)
    print(json.dumps({"track":args.track,
        "python":report["mbpp_plus"]["execution_passes"],
        "ui":report["react_ui"]["execution_passes"],
        "api":report["express_backend"]["execution_passes"],
        "total":report["overall"]["execution_passes"],
        "public_passes":public_passes,"generated_tokens":generated_tokens}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--track",choices=TRACKS,required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--batch-size",type=int,default=4)
    p.add_argument("--workers",type=int,default=2)
    run(p.parse_args())


if __name__=="__main__":
    main()
