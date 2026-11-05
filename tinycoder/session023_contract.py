"""Teacher-coached FIM transfer task, based on Session022 observed API failures.

Examples use analogous note/project resources, never FocusBoard solution
expressions. The teacher changes route response envelope scaffolding, with full
attribution in its report. The student predicts only inner data expressions.
"""
from __future__ import annotations

from .session022_contract import SLOTS, SLOT_TO_ROLE, TEMPLATES as OLD

TEMPLATES=dict(OLD)
for before,after in (
    ('res.json([[api_get]])','res.json({tasks:[[api_get]]})'),
    ('res.status(201).json([[api_post]])','res.status(201).json({task:[[api_post]]})'),
    ('res.json([[api_patch]])','res.json({task:[[api_patch]]})'),
    ('res.json([[api_delete]])','res.json({deleted:[[api_delete]]})'),
    ('res.json([[api_summary]])','res.json(processor({tasks:[[api_summary]]}))'),
):
    if before not in TEMPLATES['api']:
        raise ValueError('Old Session022 scaffold unexpectedly changed')
    TEMPLATES['api']=TEMPLATES['api'].replace(before,after)


TEACHER_LESSONS={
    'api_get':{
      'observed':'res.json(store.list())',
      'corrected':'res.json({tasks:store.list()})',
      'rule':'An API contract can require an object envelope instead of a raw array.',
      'analogy':"app.get('/api/notes', (req,res)=>res.json({notes:store.list()}));",
    },
    'api_post':{
      'observed':'res.json(undefined)',
      'corrected':'res.status(201).json({task:store.create(req.body)})',
      'rule':'Create calls the store with the request body, returns the created record and HTTP 201.',
      'analogy':"app.post('/api/notes', (req,res)=>res.status(201).json({note:store.create(req.body)}));",
    },
    'api_patch':{
      'observed':'res.json(undefined)',
      'corrected':'res.json({task:store.update(req.params.id,req.body)})',
      'rule':'A PATCH requires both the URL identifier and the JSON update body.',
      'analogy':"app.patch('/api/notes/:id',(req,res)=>res.json({note:store.update(req.params.id,req.body)}));",
    },
    'api_delete':{
      'observed':'res.json(undefined)',
      'corrected':'res.json({deleted:store.delete(req.params.id)})',
      'rule':'Delete the identified record and return the store deletion result.',
      'analogy':"app.delete('/api/notes/:id',(req,res)=>res.json({removed:store.remove(req.params.id)}));",
    },
    'api_summary':{
      'observed':'res.json(undefined)',
      'corrected':'res.json(processor({tasks:store.list()}))',
      'rule':'The summary processor receives an object containing the current task list.',
      'analogy':"app.get('/api/notes/count',(req,res)=>res.json(processor({items:store.list()})));",
    },
}


def assemble(slots):
    outputs={}
    for role,template in TEMPLATES.items():
        s=template
        for name,value in slots.items():
            s=s.replace('[['+name+']]',value)
        if '[[' in s:raise ValueError('Unfilled module slot '+role)
        outputs[role]=s
    return outputs


# Positive-control expressions for the changed teacher-provided envelopes.
# These are NEVER included in the student prompt. They are used to isolate
# one model prediction for grading, while the other routes are known-good.
REFERENCE_INNER={
    'logic_completed':"sum(1 for t in tasks if t.get('done', False))",
    'api_get':'store.list()',
    'api_post':'store.create(req.body)',
    'api_patch':'store.update(req.params.id,req.body)',
    'api_delete':'store.delete(req.params.id)',
    'api_summary':'store.list()',
    'ui_card':'<span>{task.title}</span><button onClick={onToggle}>Done</button><button onClick={onDelete}>Delete</button>',
    'css_theme':'.task-row:hover{border-color:#6178dd;}',
}


def coached_context(slot):
    """Tiny analogy-based code context; no teacher solution for task is shown."""
    lesson=TEACHER_LESSONS[slot]
    intro=("const express = require('express');\n"
           "function createApp(store,processor) {\n"
           " const app=express();\n"
           " // Verified analogous route, for learning the code pattern:\n"
           " " + lesson['analogy'] + "\n"
           " // FocusBoard required operation, use store methods:\n")
    source=TEMPLATES['api']
    row=next(line for line in source.splitlines() if '[['+slot+']]' in line)
    before,after=row.split('[['+slot+']]',1)
    return intro+before,after+'\n return app;\n}'
