"""Archive only measured teacher-student Qwen slot repairs and static UI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session023_contract import SLOTS, assemble, TEACHER_LESSONS


def collect(out):
    report=json.loads((out/'report.json').read_text(encoding='utf-8'))
    prediction=json.loads((out/'predictions.json').read_text(encoding='utf-8'))
    expected=hashlib.sha256(Path('experiments/session022_fim_app_predictions.json').read_bytes()).hexdigest()
    if (report['session']!='023' or report['model']!=MODEL_ID or
        report['parameter_count']!=MODEL_PARAMETER_COUNT or
        report['training_steps'] or report['weight_edits'] or
        report['source_session022_sha256']!=expected or
        report['holdout_consulted_during_selection'] is not False):
        raise ValueError('Teacher-student experiment provenance mismatch')
    slots=prediction['slots']
    if set(slots)!=set(SLOTS):raise ValueError('Missing student code slots')
    for role,source in assemble(slots).items():
        if source!=prediction['assembled_source'][role]:
            raise ValueError('Saved code differs from actual Qwen slots')
    if report['generated_candidate_count']!=len(prediction['candidates']):
        raise ValueError('Candidate history loss')
    if report['integrated_model_assisted_app_pass'] != (
        bool(report['selected']['holdout']['integrated']) and all(report['slot_success'].values())):
        raise ValueError('False integration claim')
    if sum(1 for x in prediction['events'] if x['stage']=='teacher-demonstration')!=len(TEACHER_LESSONS):
        raise ValueError('Missing teacher explanations')
    preview=(out/'preview'/'index.html').read_text(encoding='utf-8')
    mentor=(out/'preview'/'mentor.html').read_text(encoding='utf-8')
    for value in (preview,mentor):
        if '<script' in value.lower() or '<iframe' in value.lower():
            raise ValueError('Unsafe static preview output')
    target=Path('docs/previews/session023')
    if target.exists():raise FileExistsError('Session023 preview would overwrite prior data')
    shutil.copytree(out/'preview',target)
    for role,file in {'logic':'backend/logic.py','api':'server/routes.js',
                      'ui':'client/App.jsx','css':'client/style.css'}.items():
        dst=target/'generated'/file
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(out/'generated'/file,dst)
    save_json(Path('experiments/session023_live_mentor_report.json'),report)
    save_json(Path('experiments/session023_live_mentor_predictions.json'),prediction)
    all_good=report['integrated_model_assisted_app_pass']
    rows='\n'.join('| '+s+' | '+('PASS' if report['slot_success'][s] else 'FAIL')+' |'
                    for s in TEACHER_LESSONS)
    section=f'''## Session 023 — teacher–student coding apprenticeship

**Integrated holdout: {"PASS" if all_good else "FAIL"}.** Starting with the
Session022 real Qwen errors, a teacher supplied analogies and corrected the
API response-envelope scaffold. The frozen 0.5B base model then produced its
own five API data expressions, tested in independent Docker unit contexts.
The UI, Python and CSS contributions are genuine frozen Session022 model
outputs. The surrounding functional application is still trusted authored
scaffolding. There was **zero parameter training**, so this measures only
in-context transfer and verified external debugging memory.

| Student API slot | Independently verified |
| --- | --- |
{rows}

[Inspect teacher corrections and each student attempt](docs/previews/session023/mentor.html) ·
[View the actual Qwen-generated code and safe preview](docs/previews/session023/index.html) ·
[Read the report](experiments/session023_live_mentor_report.json) ·
[Read every token completion](experiments/session023_live_mentor_predictions.json).

The HTML previews are not a live deployed Express application and do not
establish out-of-distribution or permanent weight generalization.
'''
    readme=Path('README.md')
    contents=readme.read_text(encoding='utf-8')
    marker='# TinyCoder Weight Lab\n'
    if not contents.startswith(marker) or '## Session 023 —' in contents:
        raise ValueError('Unexpected README structure')
    readme.write_text(contents.replace(marker,marker+'\n'+section+'\n',1),encoding='utf-8')
    print(json.dumps({'integration':all_good,'api_slots':report['slot_success']}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=Path('outputs/session023'))
    collect(p.parse_args().output_dir)


if __name__=='__main__':main()
