"""Exercise the trusted Docker evaluator with known-good synthetic modules.

These human-authored sanity fixtures NEVER enter the Qwen prompt or search.
"""
from __future__ import annotations

from .session021 import test_in_docker
from .session021_contract import PUBLIC


GOOD = {
    'logic': '''def transform(payload):
    tasks = payload['tasks']
    complete = sum(bool(task.get('done', False)) for task in tasks)
    return {'total': len(tasks), 'completed': complete, 'remaining': len(tasks)-complete}
''',
    'api': '''const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  app.get('/api/tasks', (req,res)=>res.json({tasks:store.list()}));
  app.post('/api/tasks', (req,res)=>res.status(201).json({task:store.create(req.body)}));
  app.patch('/api/tasks/:id', (req,res)=>res.json({task:store.update(req.params.id,req.body)}));
  app.delete('/api/tasks/:id', (req,res)=>res.json({deleted:store.delete(req.params.id)}));
  app.get('/api/summary', (req,res)=>res.json(processor({tasks:store.list()})));
  return app;
}
''',
    'ui': '''const React = require('react');
function App(){return React.createElement('main',null,
  React.createElement('h1',null,'Tasks'),
  React.createElement('input',{placeholder:'New task'}),
  React.createElement('button',null,'Create task'));}
''',
    'css': '''body { margin:0; padding:30px; background:#eef; color:#141b3d; }
button {background:blue;color:white;padding:9px;}''',
}


def main():
    result=test_in_docker(GOOD,PUBLIC,'public')
    if not result['integrated']:
        raise RuntimeError(f'Public evaluator preflight failed: {result["failure_reasons"]}')
    print('Trusted synthetic evaluator preflight (public only): PASS', flush=True)


if __name__=='__main__':
    main()
