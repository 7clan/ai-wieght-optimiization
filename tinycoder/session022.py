"""Qwen2.5-Coder-0.5B FIM-guided FocusBoard, eight model-owned code slots.

Unlike Session021 this is NOT four fully model-authored files: the harness
provides all surrounding code. Model completions are inserted verbatim except
for generic whitespace/delimiter cleanup and saved separately for provenance.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import MODEL_ID, _torch_model, docker_command
from .session015 import MODEL_PARAMETER_COUNT
from .session022_contract import (SLOTS, SLOT_TO_ROLE, TEMPLATES,
                                  assemble, public_cases, holdout_cases)

IMAGE = 'tinycoder-session022-generated:1'
DEFAULT = {s:('0' if s=='logic_completed' else 'undefined' if s.startswith('api_')
              else '' if s=='css_theme' else '<span>Task pending</span>') for s in SLOTS}
MAX_TOKENS = {'ui_card':154,'css_theme':180}
MAX_ATTEMPTS = 9
CHECKS = {'api_get':'get','api_post':'post','api_patch':'patch',
          'api_delete':'delete','api_summary':'summary'}


def docker_test(modules, cases, phase, timeout=40):
    require_sandbox()
    with tempfile.TemporaryDirectory(prefix='qwen-fim22-') as tmp:
        root=Path(tmp)
        src,dst=root/'input',root/'out'
        src.mkdir(mode=0o755);dst.mkdir(mode=0o777)
        os.chmod(root,0o755);os.chmod(dst,0o777)
        (src/'input.json').write_text(json.dumps({'modules':modules,
            'cases':cases,'phase':phase}),encoding='utf-8')
        os.chmod(src/'input.json',0o644)
        name='qwen022-'+uuid.uuid4().hex[:14]
        cmd=docker_command(IMAGE,src,dst,name,is_web=True)
        try:
            proc=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker','rm','-f',name],check=False,capture_output=True,timeout=8)
            raise RuntimeError('Restricted Docker evaluation timed out')
        if proc.returncode or not (dst/'result.json').is_file():
            raise RuntimeError('Restricted Docker evaluator failed: '+proc.stderr[-800:])
        record=json.loads((dst/'result.json').read_text(encoding='utf-8'))
        if record.get('phase')!=phase or set(record.get('modules',{}))!=set(TEMPLATES):
            raise RuntimeError('Invalid Docker result schema')
        return record


def normalize(raw, slot):
    """Generic string/delimiter trimming; never replace model logic with an oracle."""
    value=raw.split('<|fim_suffix|>')[0].split('<|fim_middle|>')[0]
    value=value.split('<|endoftext|>')[0].split('<|im_end|>')[0]
    if slot=='css_theme':
        return value[:3000].strip()
    if slot=='ui_card':
        value=value.split('</li>')[0].split(');\n}')[0]
        return value[:2000].strip()
    value=value.splitlines()[0].strip().rstrip(';').strip()
    # Drop closing delimiters emitted for the surrounding FIM suffix.
    while value.endswith(')') and value.count(')')>value.count('('):
        value=value[:-1].rstrip()
    while value.endswith('}') and value.count('}')>value.count('{'):
        value=value[:-1].rstrip()
    return value[:400]


def valid_for(slot, outcome, candidate):
    role=SLOT_TO_ROLE[slot]
    if slot=='api_summary':
        return (outcome['checks'].get('summary') is True and
                outcome['checks'].get('integrated_api') is True)
    if slot in CHECKS:
        return outcome['checks'].get(CHECKS[slot]) is True
    if slot=='ui_card':
        return (outcome['modules']['ui']['passed'] and
                outcome['checks'].get('ui_item') is True)
    if slot=='css_theme':
        return (bool(candidate.strip()) and len(candidate)>16 and
                not re.search(r'(?i)@import|url\s*\(|expression\s*\(|behavior\s*:',candidate)
                and outcome['modules']['css']['passed'])
    return outcome['modules'][role]['passed']


def slot_context(slots, name):
    role=SLOT_TO_ROLE[name]
    replaced=TEMPLATES[role]
    for s in SLOTS:
        if s!=name:
            replaced=replaced.replace('[['+s+']]',slots[s])
    replaced=replaced.replace('[['+name+']]','<<INSERT>>')
    return replaced.split('<<INSERT>>',1)


def generate(model, tokenizer, prefix, suffix, attempt, slot):
    import torch
    torch.manual_seed(2026112200 + SLOTS.index(slot)*19 + attempt)
    # Native Qwen Coder FIM tokens, verified in the tokenizer config.
    fim='<|fim_prefix|>'+prefix+'<|fim_suffix|>'+suffix+'<|fim_middle|>'
    inputs=tokenizer(fim,return_tensors='pt',add_special_tokens=False)
    cap=MAX_TOKENS.get(slot,74)
    kwargs={'max_new_tokens':cap,'do_sample':attempt>0,
            'pad_token_id':tokenizer.eos_token_id}
    if attempt: kwargs.update({'temperature':0.65+(attempt%3)*0.1,'top_p':0.93})
    with torch.inference_mode():
        result=model.generate(**inputs,**kwargs)
    raw=tokenizer.decode(result[0,inputs['input_ids'].shape[1]:],skip_special_tokens=False)
    return raw,int(result.shape[1]-inputs['input_ids'].shape[1])


def render_preview(selected, report, path):
    """Static, sanitized viewer. Never execute model JS in the public browser."""
    from .session021 import preview_page
    preview_page(assemble(selected),{'public':report['selected']['public'],
        'holdout':report['selected']['holdout']},path)


def run(args):
    require_sandbox()
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Refusing to overwrite existing experiment outputs')
    out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    model,tokenizer=_torch_model()
    parameter_count=sum(p.numel() for p in model.parameters())
    if parameter_count!=MODEL_PARAMETER_COUNT:
        raise RuntimeError('Unexpected Qwen model size')
    selected=dict(DEFAULT)
    records=[]
    total_tokens=0
    initial=docker_test(assemble(selected),public_cases(),'public')
    print('Initial checks:',initial['checks'],flush=True)
    slot_success={}
    for name in SLOTS:
        found=False
        prefix,suffix=slot_context(selected,name)
        # No holdout examples are loaded or inspected during this search.
        for attempt in range(MAX_ATTEMPTS):
            raw,n=generate(model,tokenizer,prefix,suffix,attempt,name)
            total_tokens+=n
            value=normalize(raw,name)
            candidate=dict(selected)
            candidate[name]=value
            outcome=docker_test(assemble(candidate),public_cases(),'public')
            passed=bool(valid_for(name,outcome,value))
            records.append({'slot':name,'attempt':attempt,'raw':raw,
              'normalized':value,'tokens':n,'accepted':passed,
              'public':{'checks':outcome['checks'],
               'module_passed':outcome['modules'][SLOT_TO_ROLE[name]]['passed'],
               'error':outcome['modules'][SLOT_TO_ROLE[name]]['error']}})
            if passed:
                selected=candidate
                found=True
                print(f'ACCEPT {name}, attempt {attempt}, value {value[:100]!r}',flush=True)
                break
        slot_success[name]=found
        if not found:print(f'UNSOLVED {name}, all {MAX_ATTEMPTS} attempts',flush=True)
    del model
    gc.collect()
    public=docker_test(assemble(selected),public_cases(),'public')
    # Holdout examples are materialized for the first time AFTER selection.
    hidden=docker_test(assemble(selected),holdout_cases(),'holdout')
    integrated=bool(hidden['integrated'] and all(slot_success.values()))
    outputs=assemble(selected)
    paths={'logic':'backend/logic.py','api':'server/routes.js',
           'ui':'client/App.jsx','css':'client/style.css'}
    for role,name in paths.items():
        target=out/'generated'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(outputs[role],encoding='utf-8')
    save_json(out/'predictions.json',{'slots':selected,'records':records,
              'source':outputs,'scaffold_sha256':{
                  role:hashlib.sha256(template.encode()).hexdigest()
                  for role,template in TEMPLATES.items()}})
    report={'session':'022','status':'completed','model':MODEL_ID,
        'parameter_count':parameter_count,'training_steps':0,'weight_edits':0,
        'method':'native-FIM-code-slots-with-trusted-scaffold',
        'model_owned_slots':list(SLOTS),'slot_success':slot_success,
        'generated_candidate_count':len(records),
        'generated_output_tokens':total_tokens,
        'wall_seconds':round(time.monotonic()-start,2),
        'selected':{'public':public,'holdout':hidden},
        'all_model_slots_verified':all(slot_success.values()),
        'integrated_model_assisted_app_pass':integrated,
        'holdout_consulted_during_selection':False,
        'attribution':'Model wrote only eight insertion slots; task wiring, API routes, state and UI shell are authored trusted scaffolding. This is NOT a model-authored full app.',
        'preview_kind':'static-sanitized-only; no live deployment',
        'test_scope':'Three public and three held-out Python statistics inputs, HTTP CRUD and React SSR/TaskItem.'}
    save_json(out/'report.json',report)
    render_preview(selected,report,out/'preview'/'index.html')
    print(json.dumps({'integrated_model_assisted_pass':integrated,
         'slot_success':slot_success,'holdout':hidden['integrated'],
         'candidate_count':len(records),'tokens':total_tokens}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default='outputs/session022')
    run(parser.parse_args())


if __name__=='__main__': main()
