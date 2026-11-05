const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  app.get('/api/health', (req, res) => {
    res.status(200).send({ ok: true });
  });
  app.get('/api/entries', (req, res) => {
    const entries = store.list();
    res.status(200).json({ entries });
  });
  app.post('/api/entries', (req, res) => {
    const entry = req.body;
    const id = store.create(entry);
    res.status(201).json({ item: { id, ...entry } });
  });
  app.delete('/api/entries/:id', (req, res) => {
    store.delete(req.params.id);
    res.status(200).json({ deleted: true });
  });
  app.get('/api/projects', (req, res) => {
    const projects = store.list().map(p => p.name);
    res.status(200).json({ projects });
  });
  app.get('/api/summary', (req, res) => {
    const entries = processor({ entries: store.list() });
    res.status(200).json({ entries });
  });
  return app;
}

module.exports = createApp;