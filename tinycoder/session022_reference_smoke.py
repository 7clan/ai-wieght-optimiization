"""Prove the sandbox contract is satisfiable with an independent fixture.

This fixture is NEVER used by the Qwen candidate generator or its prompt.
"""
from .session022 import docker_test
from .session022_contract import assemble, public_cases, holdout_cases

REFERENCE = {
    'logic_completed':"sum(1 for t in tasks if t.get('done', False))",
    'api_get':'{tasks:store.list()}',
    'api_post':'{task:store.create(req.body)}',
    'api_patch':'{task:store.update(req.params.id,req.body)}',
    'api_delete':'{deleted:store.delete(req.params.id)}',
    'api_summary':'processor({tasks:store.list()})',
    'ui_card':'<span>{task.title}</span><button onClick={onToggle}>Done</button><button onClick={onDelete}>Delete</button>',
    'css_theme':'.task-row:hover { border-color: #6178dd; }',
}


def main():
    for cases,phase in ((public_cases(),'public'),(holdout_cases(),'holdout')):
        result=docker_test(assemble(REFERENCE),cases,phase)
        if not result['integrated']:
            raise RuntimeError(f'Session022 trusted preflight {phase} failed: {result["failure_reasons"]}')
    print('Sandbox validator positive control PASS',flush=True)


if __name__=='__main__': main()
