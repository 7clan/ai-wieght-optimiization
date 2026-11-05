const express = require('express');
// Build FocusBoard, a small but real task manager with a responsive React UI,
// Express JSON API, and Python task statistics. Users can create tasks, view them,
// mark them complete/incomplete, delete them, and see total/completed/remaining.
// Tasks have id (string), title (nonempty string), priority (low/medium/high),
// done (boolean). The trusted harness supplies a persistent SQLite store and
// a bridge that invokes your Python transform(payload) function. Do not copy
// the implementation from any existing repository file; write the four modules.
// 
// API contract:
//   GET /api/tasks              -> HTTP 200 {tasks:[...]}
//   POST /api/tasks             -> HTTP 201 {task:{id,title,priority,done}}
//   PATCH /api/tasks/:id        -> HTTP 200 {task:{id,title,priority,done}}
//   DELETE /api/tasks/:id       -> HTTP 200 {deleted:true}
//   GET /api/summary            -> HTTP 200 {total,completed,remaining}
// 
// The supplied store implements list(), create(body), update(id, body), delete(id).
// The supplied processor accepts {tasks: store.list()} and returns the Python
// statistics result. The generated Express module must export createApp(store,
// processor) returning an Express instance. The generated React App component
// must display a task-list heading, an entry form, complete-toggle and delete
// buttons, and fetch data from the API. Do not use any external component library.
// server/routes.js. No database or other imports.
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use(express.static('public'));
  app.get('/api/summary', (req, res) => {
    const summary = processor(store);
    res.json(summary);
  });
  app.post('/api/tasks', (req, res) => {
    const newTask = processor(store, req.body);
    res.json(newTask);
  });
  app.patch('/api/tasks/:id', (req, res) => {
    const updatedTask = processor(store, req.body);
    res.json(updatedTask);
  });
  app.delete('/api/tasks/:id', (req, res) => {
    const deletedTask = processor(store, req.params.id);
    res.json(deletedTask);
  });
  return app;
}