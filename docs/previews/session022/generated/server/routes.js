const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  // GET all tasks, response {tasks:[...]}
  app.get('/api/tasks', (req, res) => res.json(undefined));
  // POST a new task, response {task:{...}}
  app.post('/api/tasks', (req, res) => res.status(201).json(undefined));
  // PATCH /api/tasks/:id, response {task:{...}}
  app.patch('/api/tasks/:id', (req, res) => res.json(undefined));
  // DELETE /api/tasks/:id, response {deleted:boolean}
  app.delete('/api/tasks/:id', (req, res) => res.json(undefined));
  // GET /api/summary, call processor({tasks:store.list()})
  app.get('/api/summary', (req, res) => res.json(undefined));
  return app;
}
