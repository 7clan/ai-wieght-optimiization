const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  app.get('/api/items', (_req, res) => {
    res.status(200).json({items: store.list()});
  });
  app.post('/api/items', (req, res) => {
    try {
      res.status(201).json({item: store.create(req.body)});
    } catch (error) {
      res.status(400).json({error: error.message});
    }
  });
  app.delete('/api/items/:id', (req, res) => {
    res.status(200).json({deleted: store.delete(req.params.id)});
  });
  app.get('/api/summary', (_req, res) => {
    res.status(200).json(processor({items: store.list()}));
  });
  return app;
}

module.exports = createApp;