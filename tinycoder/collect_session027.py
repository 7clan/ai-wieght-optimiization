"""Verify genuine Qwen source provenance and publish failed OR passing results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session027_contract import ROLES, fingerprint, prefix


def validate(root:Path):
    report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    preds=json.loads((root/'predictions.json').read_text(encoding='utf-8'))
    if (report.get('session')!='027' or report.get('status')!='completed'
        or report.get('model')!=MODEL_ID
        or report.get('parameter_count')!=MODEL_PARAMETER_COUNT
        or report.get('training_steps')!=0 or report.get('weight_edits')!=0
        or report.get('contract_sha256')!=fingerprint()
        or report.get('model_completed_roles')!=list(ROLES)
        or report.get('search',{}).get('private_holdout_seen_during_selection') is not False):
        raise ValueError('Frozen model, contract or evaluation provenance mismatch')
    attempts=preds.get('attempts',[])
    if (len(attempts)<len(ROLES)
        or [(x.get('stage'),x.get('role')) for x in attempts[:5]]!=
           [('greedy',r) for r in ROLES]
        or report['search']['candidate_count']!=len(attempts)):
        raise ValueError('Missing raw Qwen candidate log')
    if set(preds.get('selected',{}))!=set(ROLES) or set(preds.get('greedy',{}))!=set(ROLES):
        raise ValueError('Model source set incomplete')
    for role in ROLES:
        current=preds['selected'][role]
        if not isinstance(current,str) or not current.startswith(prefix(role)):
            raise ValueError('Non-model source or changed signature: '+role)
        if (root/'generated'/ROLE_PATHS[role]).read_text(encoding='utf-8')!=current:
            raise ValueError('Generated file does not equal recorded Qwen selection')
    for track in ('baseline','selected'):
        for phase in ('public','holdout'):
            record=report[track][phase]
            if record.get('phase')!=phase or set(record.get('modules',{}))!=set(ROLES):
                raise ValueError('Changed evaluation result schema')
            if record['integrated'] and not (
                all(record['modules'][role]['passed'] for role in ROLES)
                and record['checks'].get('integration') is True):
                raise ValueError('Fabricated integrated success')
    page=(root/'preview'/'index.html').read_text(encoding='utf-8').lower()
    if '<script' in page or '<iframe' in page or '<form' in page:
        raise ValueError('Unsafe executable preview')
    return report,preds


def collect(root:Path):
    report,preds=validate(root)
    gallery=Path('docs/previews/session027')
    if gallery.exists() and any(gallery.iterdir()):
        raise FileExistsError('Existing published preview')
    gallery.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'preview'/'index.html',gallery/'index.html')
    for role,p in ROLE_PATHS.items():
        path=gallery/'generated'/p
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/'generated'/p,path)
    save_json(Path('experiments/session027_autonomous_app_report.json'),report)
    save_json(Path('experiments/session027_autonomous_app_predictions.json'),preds)
    print(json.dumps({'integrated':report['selected']['holdout']['integrated'],
                      'module_passes':{r:report['selected']['holdout']['modules'][r]['passed']
                                       for r in ROLES},
                      'candidate_count':len(preds['attempts'])}),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=Path('outputs/session027'))
    collect(parser.parse_args().output_dir)


if __name__=='__main__':
    main()
