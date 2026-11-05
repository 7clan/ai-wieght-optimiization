"""Session021: actual Qwen0.5B-generated task-board app, no training.

Four authored app-file prefixes are completed by the unmodified base model.
Public contract checks select sampled and feedback-repaired candidates. Only
after selection is frozen do holdout examples run. Generated code executes
solely inside restricted, network-disabled, unprivileged Docker containers.
"""
from __future__ import annotations

import argparse
import gc
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import _torch_model, docker_command, MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session019_previews import sanitize_markup
from .session021_contract import APP_NAME, PUBLIC, ROLES, SPEC, holdout, prompt, spec_hash


IMAGE = "tinycoder-session021-generated:1"
MAX_NEW = {"logic": 200, "api": 480, "ui": 560, "css": 300}
SEEDS = {"baseline": 202611210, "sample": 202611211,
         "repair1": 202611212, "repair2": 202611213}


def test_in_docker(modules, cases, phase, *, timeout=45):
    """Run one complete candidate in a restricted container, never the host."""
    require_sandbox()
    if set(modules) != set(ROLES) or phase not in {"public", "holdout"}:
        raise ValueError("Unexpected model artifact schema")
    with tempfile.TemporaryDirectory(prefix="qwen-app-test-") as tmp:
        root = Path(tmp)
        src, dst = root / "in", root / "out"
        src.mkdir(mode=0o755)
        dst.mkdir(mode=0o777)
        os.chmod(root, 0o755)
        request = src / "input.json"
        request.write_text(json.dumps({"modules": modules, "cases": cases,
                                       "phase": phase}), encoding="utf-8")
        os.chmod(request, 0o644)
        name = "qwen-app-" + uuid.uuid4().hex[:14]
        cmd = docker_command(IMAGE, src, dst, name, is_web=True)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           timeout=8, check=False)
            return failed(phase, "Isolated evaluator timeout")
        path = dst / "result.json"
        if result.returncode or not path.is_file():
            return failed(phase, "Docker evaluator error: " + result.stderr[-220:])
        checked = json.loads(path.read_text(encoding="utf-8"))
        if checked.get("phase") != phase or set(checked.get("modules", {})) != set(ROLES):
            raise ValueError("Docker changed report identity")
        return checked


def failed(phase, message):
    return {"phase": phase, "integrated": False, "completed_checks": 0,
            "modules": {role: {"passed": False, "syntax_valid": False,
                               "error": message} for role in ROLES},
            "checks": {}, "ui_markup": None, "failure_reasons": [message]}


def generate_one(model, tokenizer, text, *, max_tokens, seed, stochastic):
    """Pure forward-only inference with seed and token budget recorded."""
    import torch
    torch.manual_seed(seed)
    inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    kwargs = {"max_new_tokens": max_tokens, "do_sample": stochastic,
              "pad_token_id": tokenizer.eos_token_id}
    if stochastic:
        kwargs.update({"temperature": 0.72, "top_p": 0.93})
    with torch.inference_mode():
        output = model.generate(**inputs, **kwargs)
    decoded = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:],
                               skip_special_tokens=True)
    return decoded, int(output.shape[1] - inputs["input_ids"].shape[1])


def ranking(record):
    return (int(bool(record["integrated"])),
            sum(int(bool(record["modules"][role]["passed"])) for role in ROLES),
            int(record["completed_checks"]),
            sum(int(bool(record["modules"][role]["syntax_valid"])) for role in ROLES))


def repair_prompt(role, source, error):
    error = str(error or "Public contract failed").replace("\n", " ")[:240]
    lines = source[-1300:].splitlines()[-28:]
    if role == "logic":
        context = "\n".join("# " + line for line in lines)
        return (f"# Previous attempt failed: {error}\n"
                f"# Previous code excerpt:\n{context}\n" + prompt(role))
    if role == "css":
        context = "\n".join("/* " + line.replace("*/", "* / ")[:140] + " */"
                            for line in lines)
        return f"/* Previous attempt failed: {error} */\n{context}\n" + prompt(role)
    context = "\n".join("// " + line for line in lines)
    return f"// Previous attempt failed: {error}\n// Previous excerpt:\n{context}\n" + prompt(role)


TRUSTED_CSS = """
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#e4ecfa;background:#0b1220}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1120px;margin:auto;padding:54px 23px}
h1{font-size:clamp(35px,5vw,55px);letter-spacing:-.045em;margin:24px 0 12px}
p{line-height:1.6;color:#afc0d6}.lead{max-width:740px}.logo{font-size:12px;color:#8ed7e9;font-weight:800;letter-spacing:.18em}
a{color:#9be4ec}.label{font-size:12px;color:#9fb2d0}.status{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}
.badge{border-radius:99px;padding:7px 11px;background:#2c3851;font-size:12px;font-weight:750}
.good{background:#15493d;color:#a4f1d6}.bad{background:#552b37;color:#ffb2b8}
.panel{background:#162238;border:1px solid #31435e;padding:26px;border-radius:18px;margin:25px 0}
.canvas{background:#f8fafc;border-radius:14px;color:#233245;min-height:240px;padding:25px;overflow:auto}
.canvas input,.canvas button{padding:9px;border:1px solid #bac6d4;border-radius:7px;margin:6px}
.canvas button{background:#dfe8fa;color:#182d48}.canvas h1,.canvas h2{color:#172a47;font-size:25px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1424;border:1px solid #263d57;border-radius:12px;padding:18px;color:#dbe9f7;font-size:12px}
details{margin:12px 0;background:#152034;border:1px solid #30405b;border-radius:12px;padding:17px}
summary{cursor:pointer;font-weight:800}footer{margin-top:50px;border-top:1px solid #29435d;padding-top:22px;color:#94a6c0}
"""


def preview_page(modules, records, output):
    """Static script-free look at actual generated React markup and sources."""
    import re
    markup = records["holdout"].get("ui_markup") or records["public"].get("ui_markup")
    safe = sanitize_markup(markup) if markup is not None else (
        '<p>Qwen\'s React component did not render in the restricted Docker test.</p>')
    holdout_result = records["holdout"]
    badges = "".join(
        f'<span class="badge {"good" if holdout_result["modules"][r]["passed"] else "bad"}">'
        f'{r.upper()}: {"PASS" if holdout_result["modules"][r]["passed"] else "FAIL"}</span>'
        for r in ROLES)
    code = "".join(
        f'<details><summary>Actual generated {html.escape(r.upper())} source</summary>'
        f'<pre>{html.escape(modules[r])}</pre></details>' for r in ROLES)
    failures = "".join(f'<li>{html.escape(x)}</li>' for x in holdout_result.get("failure_reasons", []))
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
            f'<title>Actual Qwen0.5B app: FocusBoard</title><style>{TRUSTED_CSS}</style></head>'
            '<body><main class="wrap"><div class="logo">TINY CODER · SESSION 021</div>'
            '<h1>What did the 0.5B model actually make?</h1>'
            '<p class="lead">This page contains the real model-generated code and the React markup it rendered '
            'inside restricted Docker. The screenshot is static and script-free, not a live server. '
            'The SQLite adapter, build tools and verification tests were provided externally.</p>'
            f'<div class="status">{badges}</div>'
            f'<div class="panel"><span class="label">MODEL-RENDERED UI SNAPSHOT</span><div class="canvas">{safe}</div></div>'
            f'<div class="panel"><strong>Holdout outcome</strong><p>{"Integrated contract passed" if holdout_result["integrated"] else "Integrated contract did not pass"}.</p>'
            f'<ul>{failures}</ul></div>' + code +
            '<footer>Untrusted generated JavaScript is never served for execution in your browser. '
            'All model code was evaluated in unprivileged, network-disabled containers.</footer>'
            '</main></body></html>\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def run(args):
    require_sandbox()
    destination = Path(args.output_dir)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Refusing to overwrite generated benchmark output")
    destination.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    model, tokenizer = _torch_model()
    assert sum(p.numel() for p in model.parameters()) == MODEL_PARAMETER_COUNT
    output_tokens, candidates, accepted = 0, [], []
    selected = {}

    for i, role in enumerate(ROLES):
        raw, count = generate_one(model, tokenizer, prompt(role),
                                  max_tokens=MAX_NEW[role],seed=SEEDS['baseline']+i,
                                  stochastic=False)
        selected[role] = prompt(role) + raw
        output_tokens += count
        candidates.append({"stage": "baseline", "role": role, "raw": raw,
                           "output_tokens": count})
    baseline = dict(selected)
    baseline_public = test_in_docker(baseline, PUBLIC, "public")
    current = baseline_public
    print('Baseline module passes:',
          {r: v['passed'] for r,v in current['modules'].items()},flush=True)

    for stage in ('sample','repair1','repair2'):
        for i, role in enumerate(ROLES):
            if current['modules'][role]['passed']:
                continue
            previous = selected[role]
            query = prompt(role) if stage=='sample' else repair_prompt(
                role, previous, current['modules'][role]['error'])
            raw, count = generate_one(model, tokenizer, query,
                                      max_tokens=MAX_NEW[role],
                                      seed=SEEDS[stage]+i, stochastic=True)
            output_tokens += count
            candidate = dict(selected)
            candidate[role] = prompt(role)+raw
            outcome = test_in_docker(candidate, PUBLIC, 'public')
            improve = ranking(outcome) > ranking(current)
            candidates.append({"stage": stage, "role": role, "raw": raw,
                               "output_tokens": count, "public": outcome,
                               "accepted": improve})
            if improve:
                selected, current = candidate, outcome
                accepted.append({"stage": stage, "role": role,
                                 "score": ranking(outcome)})
        print(stage, 'public rank', ranking(current), flush=True)

    del model
    gc.collect()
    # Holdout is imported from the contract but first invoked AFTER all search.
    final_cases = holdout()
    baseline_holdout = test_in_docker(baseline, final_cases, 'holdout')
    selected_holdout = test_in_docker(selected, final_cases, 'holdout')

    save_json(destination/'predictions.json', {"baseline": baseline,
              "selected": selected, "candidates": candidates,
              "accepted": accepted})
    names = {'logic':'backend/logic.py','api':'server/routes.js',
             'ui':'client/App.jsx','css':'client/style.css'}
    for role, name in names.items():
        path = destination/'generated'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(selected[role], encoding='utf-8')
    report = {"status":"completed", "session":"021", "model":MODEL_ID,
        "parameter_count":MODEL_PARAMETER_COUNT,"training_steps":0,
        "model_weight_edits":0, "app":APP_NAME,
        "task_type":"authored_end_to_end_task_board_not_independent_benchmark",
        "spec_sha256":spec_hash(),"model_generated_roles":list(ROLES),
        "trusted_components":["SQLite store adapter","Python bridge", "Vite build",
                              "Docker test runner","preview sanitizer"],
        "baseline":{"public":baseline_public,"holdout":baseline_holdout},
        "selected":{"public":current,"holdout":selected_holdout},
        "search":{"stages":list(SEEDS),"accepted":accepted,
                  "candidate_count":len(candidates),"generated_output_tokens":output_tokens,
                  "wall_seconds":round(time.monotonic()-start,2),
                  "holdout_consulted_before_search_finished":False},
        "caveats":"Tests check generated Python, Express CRUD routes and React server-rendered structure. No browser click-through test, real model-generated persistence layer, security audit or frontier-model parity claim. This is a partially scaffolded full-stack system; failures remain visible."}
    save_json(destination/'report.json',report)
    preview_page(selected,{'public':current,'holdout':selected_holdout},
                 destination/'preview'/'index.html')
    print(json.dumps({"baseline_pass":baseline_holdout['integrated'],
                      "selected_pass":selected_holdout['integrated'],
                      "module_passes":{r:v['passed'] for r,v in selected_holdout['modules'].items()},
                      "generated_tokens":output_tokens}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default='outputs/session021')
    run(parser.parse_args())


if __name__=='__main__':
    main()
