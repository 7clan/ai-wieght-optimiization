"""Targeted Qwen0.5B student replay after teacher corrects `remove` vs `delete`.

Exactly one previously failing API expression is regenerated. No training.
The analogous route demonstrates the same store.delete signature; this is
few-shot imitation and MUST NOT be called novel transfer generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import MODEL_ID, _torch_model
from .session015 import MODEL_PARAMETER_COUNT
from .session021_contract import PUBLIC, holdout
from .session022 import docker_test, generate, normalize
from .session023 import mentor_view
from .session023_contract import assemble


def delete_context():
    """Only a related notes route, not a complete FocusBoard source file."""
    prefix=("const express=require('express');\n"
       "function createApp(store, processor) {\n"
       " const app=express();\n"
       " // Available store methods: list(), create(body), update(id,body), delete(id).\n"
       " // Mentor fixed this related resource deletion using the interface:\n"
       " app.delete('/api/notes/:id',(req,res)=>res.json({removed:store.delete(req.params.id)}));\n"
       " // Complete the task deletion using the same verified method.\n"
       " app.delete('/api/tasks/:id',(req,res)=>res.json({deleted:")
    suffix="}));\n return app;\n}"
    return prefix,suffix


def run(args):
    require_sandbox()
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):raise FileExistsError('Refusing to overwrite')
    out.mkdir(parents=True,exist_ok=True)
    previous_path=Path('experiments/session023_live_mentor_predictions.json')
    previous=json.loads(previous_path.read_text(encoding='utf-8'))
    prior=json.loads(Path('experiments/session023_live_mentor_report.json').read_text(encoding='utf-8'))
    if (prior['parameter_count']!=MODEL_PARAMETER_COUNT or
        prior['integrated_model_assisted_app_pass'] or
        [k for k,v in prior['slot_success'].items() if not v]!=['api_delete']):
        raise RuntimeError('Actual Session023 DELETE-only failure no longer matches')
    selected=dict(previous['slots'])
    if selected['api_delete']!='undefined':
        raise RuntimeError('Session023 failed DELETE was not preserved exactly')
    prefix,suffix=delete_context()
    events=[{'stage':'teacher-demonstration','slot':'api_delete',
      'summary':'Teacher catches method-name confusion from Session023',
      'before':'store.remove(req.params.id)',
      'after':'store.delete(req.params.id)',
      'rule':'Use the explicitly documented delete(id) store method. The prior remove() analogy did not match this API.'}]
    model,tokenizer=_torch_model()
    count=sum(p.numel() for p in model.parameters())
    if count!=MODEL_PARAMETER_COUNT:raise RuntimeError('Unexpected model parameter count')
    records=[]
    generated_tokens=0
    passed=False
    start=time.monotonic()
    for attempt in range(14):
        raw,tokens=generate(model,tokenizer,prefix,suffix,attempt,'api_delete')
        value=normalize(raw,'api_delete')
        generated_tokens+=tokens
        case=dict(selected);case['api_delete']=value
        result=docker_test(assemble(case),PUBLIC,'public')
        accepted=(result['checks'].get('delete') is True and
                  result['checks'].get('integrated_api') is True)
        records.append({'attempt':attempt,'raw':raw,'normalized':value,
                        'tokens':tokens,'accepted':accepted,
                        'public_checks':result['checks'],
                        'error':result['modules']['api']['error']})
        events.append({'stage':'student-attempt','slot':'api_delete',
                       'summary':'Qwen student delete repair '+str(attempt+1),
                       'student':value,'passed':accepted})
        print('STUDENT REPAIR delete',attempt,'PASS' if accepted else 'FAIL',repr(value),flush=True)
        if accepted:
            selected=case;passed=True
            break
    del model
    public=docker_test(assemble(selected),PUBLIC,'public')
    # Holdout examples are loaded only once the student choice is frozen.
    hidden=docker_test(assemble(selected),holdout(),'holdout')
    integrated=bool(passed and public['integrated'] and hidden['integrated'])
    source=assemble(selected)
    report={'session':'024','status':'completed','model':MODEL_ID,
      'parameter_count':count,'training_steps':0,'weight_edits':0,
      'student_slot':'api_delete','student_success':passed,
      'generated_candidate_count':len(records),
      'generated_output_tokens':generated_tokens,
      'wall_seconds':round(time.monotonic()-start,2),
      'selected':{'public':public,'holdout':hidden},
      'integrated_model_assisted_app_pass':integrated,
      'teacher_lessons':'Session023 failed on remove() method; Session024 teacher explicitly showed delete(id) method and analogous notes route.',
      'attribution':'Qwen wrote eight verified functional expressions/JSX/CSS segments across Sessions022-024; API envelope, route wiring, React app logic, Python function wrapper and storage adapter were trusted authored scaffolds.',
      'holdout_consulted_during_selection':False,
      'permanent_weight_learning_proven':False,
      'independent_transfer_proven':False,
      'previous_predictions_sha256':hashlib.sha256(previous_path.read_bytes()).hexdigest()}
    save_json(out/'report.json',report)
    save_json(out/'predictions.json',{'slots':selected,'candidates':records,
                                    'events':events,'assembled_source':source})
    for role,path in {'logic':'backend/logic.py','api':'server/routes.js',
                      'ui':'client/App.jsx','css':'client/style.css'}.items():
        dest=out/'generated'/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(source[role],encoding='utf-8')
    from .session021 import preview_page
    preview_page(source,{'public':public,'holdout':hidden},out/'preview'/'index.html')
    mentor_view(events,report,{'slots':selected},out/'preview'/'mentor.html')
    print(json.dumps({'integrated':integrated,'slot_success':passed,
                      'holdout':hidden['integrated']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',default='outputs/session024')
    run(p.parse_args())


if __name__=='__main__':main()
