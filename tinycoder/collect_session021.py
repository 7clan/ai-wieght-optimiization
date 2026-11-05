"""Strictly validate measured Session021 and export real generated source/preview."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session015 import MODEL_PARAMETER_COUNT
from .session021_contract import ROLES, spec_hash
from .session014 import MODEL_ID


BEGIN = '<!-- SESSION021-GENERATED-APP-START -->'
END = '<!-- SESSION021-GENERATED-APP-END -->'


def validate(output):
    report = json.loads((output/'report.json').read_text(encoding='utf-8'))
    predictions = json.loads((output/'predictions.json').read_text(encoding='utf-8'))
    if (report.get('status')!='completed' or report.get('model')!=MODEL_ID
        or report.get('parameter_count')!=MODEL_PARAMETER_COUNT
        or report.get('training_steps')!=0 or report.get('model_weight_edits')!=0
        or report.get('spec_sha256')!=spec_hash()
        or report.get('model_generated_roles')!=list(ROLES)):
        raise ValueError('Model provenance or frozen contract mismatch')
    for track in ('baseline','selected'):
        if set(predictions.get(track,{}))!=set(ROLES):
            raise ValueError('Missing generated model source '+track)
        for role in ROLES:
            if not isinstance(predictions[track][role],str) or len(predictions[track][role])>40000:
                raise ValueError('Invalid model source '+role)
        for phase in ('public','holdout'):
            result=report[track][phase]
            if (result.get('phase')!=phase or set(result.get('modules',{}))!=set(ROLES)
                or not isinstance(result.get('integrated'),bool)
                or not isinstance(result.get('completed_checks'),int)):
                raise ValueError('Invalid measured result')
            if result['integrated'] and not all(result['modules'][role]['passed'] for role in ROLES):
                raise ValueError('False integrated pass')
    candidates=predictions.get('candidates',[])
    if len(candidates)<4 or [(x.get('stage'),x.get('role')) for x in candidates[:4]]!=[
        ('baseline',role) for role in ROLES
    ]:
        raise ValueError('Missing candidate log')
    if report['search'].get('holdout_consulted_before_search_finished') is not False:
        raise ValueError('Holdout contaminated search')
    if report['search']['candidate_count']!=len(predictions['candidates']):
        raise ValueError('Candidate count mismatch')
    for role,path in {'logic':'backend/logic.py','api':'server/routes.js',
                      'ui':'client/App.jsx','css':'client/style.css'}.items():
        if (output/'generated'/path).read_text(encoding='utf-8')!=predictions['selected'][role]:
            raise ValueError('Saved generated file changed after scoring')
    preview=(output/'preview'/'index.html').read_text(encoding='utf-8')
    if '<script' in preview.lower() or '<iframe' in preview.lower() or '<form' in preview.lower():
        raise ValueError('Unsafe live/executable HTML preview')
    return report, predictions


def collect(output, readme, experiments, gallery):
    report,predictions=validate(output)
    if gallery.exists() and any(gallery.iterdir()):
        raise FileExistsError('Refusing to overwrite published preview')
    gallery.mkdir(parents=True,exist_ok=True)
    shutil.copy2(output/'preview'/'index.html',gallery/'index.html')
    for role,path in {'logic':'backend/logic.py','api':'server/routes.js',
                      'ui':'client/App.jsx','css':'client/style.css'}.items():
        target=gallery/'generated'/path
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(output/'generated'/path,target)
    save_json(experiments/'session021_generated_app_report.json',report)
    save_json(experiments/'session021_generated_app_predictions.json',predictions)
    holdout=report['selected']['holdout']
    status='PASS' if holdout['integrated'] else 'FAIL'
    rows='\n'.join(f'| {role} | {"PASS" if holdout["modules"][role]["passed"] else "FAIL"} | '
                    f'{"YES" if holdout["modules"][role]["syntax_valid"] else "NO"} |'
                    for role in ROLES)
    section=f'''## Session 021 — actual Qwen0.5B-generated FocusBoard application

The **frozen base Qwen2.5-Coder-0.5B** generated the Python logic, Express
routes, React app and CSS directly. Every original completion, sampled attempt,
feedback repair and selection is archived. No gradients, adapters or weight
changes were used. A trusted SQLite adapter, bridge and build/test environment
were supplied separately; this is **not independent autonomous infrastructure**.

**Integrated contract result: {status}** (selected after bounded public tests).

| Model-written module | Holdout contract | Syntax |
| --- | --- | --- |
{rows}

**[View Qwen's actual UI preview and generated source](docs/previews/session021/index.html)**
(static, script-free: **not** a running Express application).

[Exact model predictions and repair history](experiments/session021_generated_app_predictions.json) ·
[Measured report](experiments/session021_generated_app_report.json).

This is one custom application and limited contract testing, not evidence of
production-grade software or parity with frontier coding systems. It does not
include an interactive browser-end-to-end assertion suite or security audit.
'''
    contents=readme.read_text(encoding='utf-8')
    if BEGIN in contents or END in contents:
        raise ValueError('Session021 report already present')
    pending_start='<!-- SESSION021-PENDING-START -->'
    pending_end='<!-- SESSION021-PENDING-END -->'
    if pending_start in contents or pending_end in contents:
        if contents.count(pending_start)!=1 or contents.count(pending_end)!=1:
            raise ValueError('Malformed pending Session021 README block')
        before,after=contents.split(pending_start,1)
        _,tail=after.split(pending_end,1)
        contents=before+tail.lstrip('\n')
    marker='# TinyCoder Weight Lab\n'
    if not contents.startswith(marker):
        raise ValueError('Unexpected README title')
    readme.write_text(contents.replace(marker,marker+'\n'+BEGIN+'\n'+section+END+'\n',1),
                      encoding='utf-8')
    print(json.dumps({'integrated_holdout':holdout['integrated'],
          'module_passed':{r:holdout['modules'][r]['passed'] for r in ROLES},
          'generated_output_tokens':report['search']['generated_output_tokens']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('outputs/session021'))
    parser.add_argument('--readme',type=Path,default=Path('README.md'))
    parser.add_argument('--experiments',type=Path,default=Path('experiments'))
    parser.add_argument('--gallery',type=Path,default=Path('docs/previews/session021'))
    args=parser.parse_args()
    collect(args.output_dir,args.readme,args.experiments,args.gallery)


if __name__=='__main__':
    main()
