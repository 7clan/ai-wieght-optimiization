const express = require('express');
function createApp(store, processor) {
  let app = express();
  app.use(express.json());
  //  GET /api/health
  app.get('/api/health', function (req, res) {
    res.status(200).json({ ok: true });
  });
  //  GET /api/entries
  app.get('/api/entries', function (req, res) {
    const entries = store.list();
    res.status(200).json({ entries });
  });
  //  POST /api/entries
  app.post('/api/entries', function (req, res) {
    const entry = req.body;
    store.create(entry)
      .then((item) => res.status(201).json({ item }))
      .catch((err) => {
        res.status(400).json({ error: 'Invalid entry' });
      });
  });
  //  DELETE /api/entries/:id
  app.delete('/api/entries/:id', function (req, res) {
    const id = req.params.id;
    store.delete(id)
      .then((deleted) => {
        if (deleted) {
          res.status(200).json({ deleted });
        } else {
          res.status(404).json({ error: 'Entry not found' });
        }
      })
      .catch((err) => {
        res.status(404).json({ error: 'Entry not found' });
      });
  });
  //  GET /api/projects
  app.get('/api/projects', function (req, res) {
    const projects = store.list().map((p) => ({
      name: p.name,
    }));
    res.status(200).json({ projects });
  });
  //  GET /api/summary
  app.get('/api/summary', function (req, res) {
    const entries = store.list();
    const project = req.query.project;
    const minutes = req.query.minutes;
    const date = req.query.date;
    const note = req.query.note;
    const entriesWithProject = entries
      .filter((e) => (project ? e.project === project : true))
      .filter((e) => (minutes ? e.minutes >= minutes : true))
      .filter((e) => (date ? e.date >= date : true))
      .filter((e) => (note ? e.note.indexOf(note) >= 0 : true))
      .sort((a, b) => {
        const dateA = new Date(a.date);
        const dateB = new Date(b.date);
        if (dateA > dateB) {
          return 1;
        }
        if (dateA < dateB) {
          return -1;
        }
        return 0;
      });
    const projectNames = entriesWithProject.map((e) => e.project);
    const projectNamesSorted = projectNames.sort();
    res.status(200).json({ entries: entriesWithProject, projectNamesSorted });
  });
  //  ENDPOINTS
  return app;
}
module.exports = createApp;