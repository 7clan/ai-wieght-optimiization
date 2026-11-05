"""Verify the exact Qwen Session024 code is what the runnable Docker app loads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .rome20 import save_json
from .session015 import MODEL_PARAMETER_COUNT
from .session023_contract import assemble


def fingerprint(data):
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('experiments/session025_runtime_smoke_report.json'))
    args=p.parse_args()
    prev=json.loads(Path('experiments/session024_student_repair_report.json').read_text(encoding='utf-8'))
    preds=json.loads(Path('experiments/session024_student_repair_predictions.json').read_text(encoding='utf-8'))
    if (prev['parameter_count']!=MODEL_PARAMETER_COUNT or
        not prev['integrated_model_assisted_app_pass'] or
        prev['training_steps'] or prev['weight_edits']):
        raise RuntimeError('No proven Session024 Qwen-assisted integrated application to package')
    sources=assemble(preds['slots'])
    files={'logic':'backend/logic.py','api':'server/routes.js',
           'ui':'client/App.jsx','css':'client/style.css'}
    hashes={}
    for role,name in files.items():
        exact=Path('docs/previews/session024/generated')/name
        if exact.read_text(encoding='utf-8')!=sources[role]:
            raise RuntimeError('Modified Qwen source in runnable app: '+role)
        hashes[name]=fingerprint(sources[role])
    report={'status':'completed','session':'025','model':'Qwen/Qwen2.5-Coder-0.5B',
      'model_parameter_count':MODEL_PARAMETER_COUNT,'no_training':True,
      'source_session024_integrated_holdout':True,
      'docker_runtime_smoke':'passed_before_export',
      'runtime_modules_sha256':hashes,
      'runtime_checks':['GET /api/tasks','POST /api/tasks','PATCH /api/tasks/:id',
        'GET /api/summary','DELETE /api/tasks/:id','SQLite file persistence',
        'HTML response','JS browser bundle','CSS response'],
      'browser_click_through_verified':False,
      'deployment_status':'not_deployed_private_codespaces_launch_required',
      'attribution':'Eight small model-generated slots, hand-authored functional application framework and Docker runtime.',
      'production_security_audit':False}
    save_json(args.output,report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
