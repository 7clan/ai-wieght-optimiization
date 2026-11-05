"""Verify actual replay output and publish only measured student repairs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session023_contract import assemble


def collect(out):
    report=json.loads((out/'report.json').read_text(encoding='utf-8'))
    prediction=json.loads((out/'predictions.json').read_text(encoding='utf-8'))
    prev=Path('experiments/session023_live_mentor_predictions.json')
    if (report['session']!='024' or report['model']!=MODEL_ID or
        report['parameter_count']!=MODEL_PARAMETER_COUNT or
        report['training_steps']!=0 or report['weight_edits']!=0 or
        report['previous_predictions_sha256']!=hashlib.sha256(prev.read_bytes()).hexdigest() or
        report['generated_candidate_count']!=len(prediction['candidates']) or
        report['holdout_consulted_during_selection'] is not False):
        raise ValueError('Replayed student model provenance mismatch')
    actual=assemble(prediction['slots'])
    if actual!=prediction['assembled_source']:
        raise ValueError('Selected model source differs from reported source')
    if report['integrated_model_assisted_app_pass'] != (
        report['student_success'] and report['selected']['public']['integrated']
        and report['selected']['holdout']['integrated']):
        raise ValueError('Incorrect success attribution')
    if report['student_success'] and not any(x['accepted'] for x in prediction['candidates']):
        raise ValueError('No independently generated successful student candidate')
    destination=Path('docs/previews/session024')
    if destination.exists():raise FileExistsError('Existing Session024 result directory')
    for name in ('index.html','mentor.html'):
        page=(out/'preview'/name).read_text(encoding='utf-8')
        if '<script' in page.lower() or '<iframe' in page.lower():
            raise ValueError('Unsafe published source viewer')
    shutil.copytree(out/'preview',destination)
    for role,p in {'logic':'backend/logic.py','api':'server/routes.js',
                   'ui':'client/App.jsx','css':'client/style.css'}.items():
        contents=(out/'generated'/p).read_text(encoding='utf-8')
        if contents!=actual[role]:raise ValueError('Saved generated source mismatch')
        new=destination/'generated'/p
        new.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(out/'generated'/p,new)
    save_json(Path('experiments/session024_student_repair_report.json'),report)
    save_json(Path('experiments/session024_student_repair_predictions.json'),prediction)
    status='PASS' if report['integrated_model_assisted_app_pass'] else 'FAIL'
    section=f'''## Session 024 — mentor-assisted final Express DELETE repair

**Full integrated holdout contract: {status}.** Qwen2.5-Coder-0.5B saw a
teacher-authored *analogy* for `store.delete(id)` and attempted the previously
unsolved DELETE expression. All eight completed slots in the final application
must come from the genuine model outputs archived in Sessions022–024.
The surrounding scaffold, API envelope, persistence and React state remain
teacher/agent-written infrastructure. This is *in-context adaptation*, not
permanent weight learning, independent generalization or an unassisted full
application created by the 0.5B model.

[View exact corrected student code and static snapshot](docs/previews/session024/index.html) ·
[Inspect teacher/student steps](docs/previews/session024/mentor.html) ·
[Measured results](experiments/session024_student_repair_report.json) ·
[Every generated attempt](experiments/session024_student_repair_predictions.json).

The preview is static and cannot be used as a deployed full-stack application.
'''
    readme=Path('README.md')
    value=readme.read_text(encoding='utf-8')
    anchor='# TinyCoder Weight Lab\n'
    if not value.startswith(anchor) or '## Session 024 —' in value:
        raise ValueError('Unexpected README')
    readme.write_text(value.replace(anchor,anchor+'\n'+section+'\n',1),encoding='utf-8')
    print(json.dumps({'integrated':status,'candidate_count':report['generated_candidate_count']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=Path('outputs/session024'))
    collect(p.parse_args().output_dir)


if __name__=='__main__':main()
