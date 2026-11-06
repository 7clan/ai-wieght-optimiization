const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  // 
  app.get('/api/health', (req, res) => {
    res.status(200).json({ ok: true });
  });
  // 
  app.post('/api/entries', (req, res) => {
    try {
      const { project, minutes, date, note } = req.body;
      const entry = {
        project,
        minutes,
        date,
        note,
      };
      store.create(entry);
      res.status(201).json({ item: entry });
    } catch (err) {
      res.status(400).json({ error: 'Invalid entry' });
    }
  });
  // 
  app.delete('/api/entries/:id', (req, res) => {
    const { id } = req.params;
    const deleted = store.delete(id);
    res.status(200).json({ deleted });
  });
  // 
  app.get('/api/projects', (req, res) => {
    const projects = store.list().map(p => p.name);
    res.status(200).json({ projects });
  });
  // 
  app.get('/api/summary', (req, res) => {
    const entries = processor({ entries: store.list() });
    res.status(200).json({ entries });
  });
  return app;
}
module.exports = createApp;