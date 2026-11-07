const express = require('express');
function createApi(app, store, processor) {
  app.use(express.json());
  app.get('/api/health', (req, res) => {
    res.status(200).json({ok: true});
  });
  app.post('/api/projects', (req, res) => {
    try {
      const project = store.createProject(req.body);
      res.status(201).json({ project: project });
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  });
  app.get('/api/projects', (req, res) => {
    const projects = store.listProjects();
    res.status(200).json({ projects });
  });
  app.put('/api/projects/:id', (req, res) => {
    // YOUR CODE HERE
    try {
      const project = store.updateProject(req.params.id, req.body);
      res.status(200).json({ project: project });
    } catch (e) {
      if (String(e.message).includes('not found')) {
        res.status(404).json({ error: e.message });
      } else {
        res.status(400).json({ error: e.message });
      }
    }
  });
  app.post('/api/tasks', (req, res) => {
    try {
      const task = store.createTask(req.body);
      res.status(201).json({ task: task });
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  });
  app.put('/api/tasks/:id', (req, res) => {
    try {
      const task = store.updateTask(req.params.id, req.body);
      res.status(200).json({ task: task });
    } catch (e) {
      if (String(e.message).includes('not found')) {
        res.status(404).json({ error: e.message });
      } else {
        res.status(400).json({ error: e.message });
      }
    }
  });
  app.get('/api/tasks', (req, res) => {
    const filter = {};
    if (req.query.projectId !== undefined) filter.projectId = req.query.projectId;
    if (req.query.status !== undefined) filter.status = req.query.status;
    if (req.query.q !== undefined) filter.q = req.query.q;
    res.status(200).json({ tasks: store.listTasks(filter) });
  });
  app.delete('/api/tasks/:id', (req, res) => {
    try {
      store.deleteTask(req.params.id);
      res.status(200).json({ deleted: true });
    } catch (e) {
      if (String(e.message).includes('not found')) {
        res.status(404).json({ error: e.message });
      } else {
        res.status(400).json({ error: e.message });
      }
    }
  });
  app.delete('/api/projects/:id', (req, res) => {
    // YOUR CODE HERE
    try {
      store.deleteProject(req.params.id);
      res.status(200).json({ deleted: true });
    } catch (e) {
      if (String(e.message).includes('not found')) {
        res.status(404).json({ error: e.message });
      } else {
        res.status(400).json({ error: e.message });
      }
    }
  });
  app.get('/api/projects/:id/progress', (req, res) => {
    const project = store.listProjects().find(p => p.id === req.params.id);
    if (!project) {
      res.status(404).json({ error: 'project not found: ' + req.params.id });
      return;
    }
    const tasks = store.listTasks({ projectId: req.params.id });
    res.status(200).json(processor({ project: project, tasks: tasks }));
  });
}
module.exports = createApi;
