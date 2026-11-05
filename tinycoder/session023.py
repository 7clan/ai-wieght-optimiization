"""Session023: teacher-observed failure -> analogy -> Qwen independent repair.

This is retrieval-guided in-context adaptation, NOT permanent weight learning.
The verified teacher reference is used only for independent candidate grading,
never fed verbatim to the student's prompts or returned as a student answer.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import time

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import _torch_model, MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session021_contract import PUBLIC, holdout
from .session022 import docker_test, generate, normalize, valid_for
from .session023_contract import (SLOTS, SLOT_TO_ROLE, TEMPLATES,
                                  TEACHER_LESSONS, REFERENCE_INNER,
                                  assemble, coached_context)

API_SLOTS=tuple(x for x in SLOTS if x.startswith('api_'))
MAX_ATTEMPTS=12


def mentor_view(events, report, predictions, dst):
    """Inspect the teacher's observable edits and every student attempt."""
    rows=[]
    for event in events:
        stage=html.escape(event['stage'])
        title=html.escape(event['slot'])
        summary=html.escape(str(event.get('summary','')))
        body=''
        if 'before' in event:
            body='<h4>Observed incorrect form</h4><pre>'+html.escape(event['before'])+'</pre>'
            body+='<h4>Teacher correction</h4><pre>'+html.escape(event['after'])+'</pre>'
            body+='<p>'+html.escape(event['rule'])+'</p>'
        if 'student' in event:
            body='<pre>'+html.escape(str(event['student']))+'</pre>'
            body+='<p>Sandbox public check: '+('PASS' if event['passed'] else 'FAIL')+'</p>'
        rows.append('<article><div class="meta">'+stage+' · '+title+'</div><h3>'+summary+'</h3>'+body+'</article>')
    passed=report['integrated_model_assisted_app_pass']
    html_page=('<!doctype html><html lang="en"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;">'
      '<title>Qwen0.5B Live Mentor Log</title><style>body{background:#0b1222;color:#e9f1ff;font:16px system-ui;margin:0}'
      'main{max-width:980px;margin:auto;padding:42px 22px}p{color:#adbeda;line-height:1.5}'
      'h1{font-size:clamp(30px,4vw,54px)}.meta{font-size:12px;letter-spacing:.1em;color:#88d9ee}'
      'article{background:#17243b;border:1px solid #364765;padding:24px;border-radius:16px;margin:16px 0}'
      'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1528;border-radius:10px;padding:18px}'
      '.result{padding:15px;border-radius:12px;background:'+( '#225443' if passed else '#652c40')+'}</style></head>'
      '<body><main><div class="meta">TINY CODER · SESSION 023</div><h1>Watch the mentor teach Qwen.</h1>'
      '<p>Each card records a test-observed error, a teacher-authored correction or an independently generated '
      'student candidate. This is an archival timeline, not a live browser stream or proof of permanent learning.</p>'
      '<div class="result">Integrated holdout: '+('PASS' if passed else 'FAIL')+'</div>'
      +''.join(rows)+'</main></body></html>\n')
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(html_page,encoding='utf-8')


def run(args):
    require_sandbox()
    dest=Path(args.output_dir)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError('Refusing to overwrite old mentor experiment')
    dest.mkdir(parents=True,exist_ok=True)
    previous=json.loads(Path('experiments/session022_fim_app_predictions.json').read_text(encoding='utf-8'))
    prior_report=json.loads(Path('experiments/session022_fim_app_report.json').read_text(encoding='utf-8'))
    if (prior_report['parameter_count']!=MODEL_PARAMETER_COUNT or
        prior_report['integrated_model_assisted_app_pass'] or
        not all(prior_report['slot_success'][s] for s in ('logic_completed','ui_card','css_theme'))):
        raise ValueError('Missing verified Session022 failure baseline')
    selected={key:previous['slots'][key] if not key.startswith('api_') else 'undefined'
              for key in SLOTS}
    events=[]
    for slot in API_SLOTS:
        l=TEACHER_LESSONS[slot]
        e={'stage':'teacher-demonstration','slot':slot,
           'summary':'Teacher explains response-contract mismatch',
           'before':l['observed'],'after':l['corrected'],
           'rule':l['rule'],'analogy':l['analogy']}
        events.append(e)
        print('TEACH',slot,l['rule'],flush=True)
    model,tokenizer=_torch_model()
    model_count=sum(p.numel() for p in model.parameters())
    if model_count!=MODEL_PARAMETER_COUNT:raise RuntimeError('Model changed unexpectedly')
    total_tokens=0
    candidates=[]
    good={}
    start=time.monotonic()
    for slot in API_SLOTS:
        prefix,suffix=coached_context(slot)
        # A target-specific correct completion never appears in the prompt.
        if TEACHER_LESSONS[slot]['corrected'] in prefix+suffix:
            raise RuntimeError('Teacher leaked target answer into student prompt')
        solved=False
        for attempt in range(MAX_ATTEMPTS):
            raw,n=generate(model,tokenizer,prefix,suffix,attempt,slot)
            value=normalize(raw,slot)
            total_tokens+=n
            # The fixture supplies DIFFERENT slots only while grading this
            # one slot. The reference does not enter the model context.
            isolated=dict(REFERENCE_INNER)
            isolated[slot]=value
            outcome=docker_test(assemble(isolated),PUBLIC,'public')
            passed=bool(valid_for(slot,outcome,value))
            candidates.append({'slot':slot,'attempt':attempt,'raw':raw,
                               'normalized':value,'accepted':passed,
                               'public_checks':outcome['checks'],
                               'api_error':outcome['modules']['api']['error'],
                               'generated_tokens':n})
            events.append({'stage':'student-attempt','slot':slot,
                           'summary':'Qwen independent repair candidate '+str(attempt+1),
                           'student':value,'passed':passed})
            print('STUDENT',slot,'attempt',attempt,'PASS' if passed else 'FAIL',repr(value[:120]),flush=True)
            if passed:
                selected[slot]=value
                solved=True
                print('LEARNED-IN-CONTEXT',slot,flush=True)
                break
        good[slot]=solved
    del model
    public=docker_test(assemble(selected),PUBLIC,'public')
    # Independent holdout is first invoked after all student selections.
    hold=docker_test(assemble(selected),holdout(),'holdout')
    integrated=bool(hold['integrated'] and all(good.values()))
    report={'session':'023','status':'completed','model':MODEL_ID,
        'parameter_count':model_count,'training_steps':0,'weight_edits':0,
        'learning_mode':'teacher-analogy-and-verified-external-memory',
        'teacher_correction_count':len(TEACHER_LESSONS),
        'student_slots':list(API_SLOTS),'slot_success':good,
        'generated_candidate_count':len(candidates),
        'generated_output_tokens':total_tokens,
        'wall_seconds':round(time.monotonic()-start,2),
        'integrated_model_assisted_app_pass':integrated,
        'selected':{'public':public,'holdout':hold},
        'holdout_consulted_during_selection':False,
        'model_origin':'Qwen wrote only API expression slots, and Session022 model-written Python, JSX and CSS slots were reused exactly.',
        'trusted_origin':'Teacher changed response envelopes and authored analogous note examples. Express routing, React App shell and Python function template remain trusted scaffolding.',
        'permanent_weight_learning_proven':False,
        'out_of_distribution_transfer_proven':False,
        'source_session022_sha256':hashlib.sha256(Path('experiments/session022_fim_app_predictions.json').read_bytes()).hexdigest()}
    source=assemble(selected)
    save_json(dest/'predictions.json',{'slots':selected,'candidates':candidates,
            'events':events,'assembled_source':source})
    for role,filename in {'logic':'backend/logic.py','api':'server/routes.js',
           'ui':'client/App.jsx','css':'client/style.css'}.items():
        path=dest/'generated'/filename
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(source[role],encoding='utf-8')
    save_json(dest/'report.json',report)
    from .session021 import preview_page
    preview_page(source,{'public':public,'holdout':hold},dest/'preview'/'index.html')
    mentor_view(events,report,{'slots':selected},dest/'preview'/'mentor.html')
    print(json.dumps({'integration':integrated,'api_slots':good,'tokens':total_tokens}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',default='outputs/session023')
    run(p.parse_args())


if __name__=='__main__':main()
