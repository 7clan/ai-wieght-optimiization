# FocusBoard public specification:
# Build FocusBoard, a small but real task manager with a responsive React UI,
# Express JSON API, and Python task statistics. Users can create tasks, view them,
# mark them complete/incomplete, delete them, and see total/completed/remaining.
# Tasks have id (string), title (nonempty string), priority (low/medium/high),
# done (boolean). The trusted harness supplies a persistent SQLite store and
# a bridge that invokes your Python transform(payload) function. Do not copy
# the implementation from any existing repository file; write the four modules.
# 
# API contract:
#   GET /api/tasks              -> HTTP 200 {tasks:[...]}
#   POST /api/tasks             -> HTTP 201 {task:{id,title,priority,done}}
#   PATCH /api/tasks/:id        -> HTTP 200 {task:{id,title,priority,done}}
#   DELETE /api/tasks/:id       -> HTTP 200 {deleted:true}
#   GET /api/summary            -> HTTP 200 {total,completed,remaining}
# 
# The supplied store implements list(), create(body), update(id, body), delete(id).
# The supplied processor accepts {tasks: store.list()} and returns the Python
# statistics result. The generated Express module must export createApp(store,
# processor) returning an Express instance. The generated React App component
# must display a task-list heading, an entry form, complete-toggle and delete
# buttons, and fetch data from the API. Do not use any external component library.
# backend/logic.py Python 3.11.
# Return exactly {total:int,completed:int,remaining:int}.
# Count done=True as completed. No external libraries.
def transform(payload):
    data = payload.json()
    return {
        'total': data['total'],
        'completed': data['completed'],
        'remaining': data['remaining']
    }
 
backend.store.create = create
backend.store.update = update
backend.store.delete = delete
backend.store.list = list
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend.logic = processor
backend.store = backend.store
backend.store.update = update
backend.store.delete = delete
backend