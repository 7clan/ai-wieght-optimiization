const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  // GET all tasks, response {tasks:[...]}
  app.get('/api/tasks', (req, res) => res.json({tasks:store.list()}));
  // POST a new task, response {task:{...}}
  app.post('/api/tasks', (req, res) => res.status(201).json({task:store.create(req.body)}));
  // PATCH /api/tasks/:id, response {task:{...}}
  app.patch('/api/tasks/:id', (req, res) => res.json({task:store.update(req.params.id,req.body)}));
  // DELETE /api/tasks/:id, response {deleted:boolean}
  app.delete('/api/tasks/:id', (req, res) => res.json({deleted:undefined}));
  // GET /api/summary, call processor({tasks:store.list()})
  app.get('/api/summary', (req, res) => res.json(processor({tasks:store.list()})));
  return app;
}
