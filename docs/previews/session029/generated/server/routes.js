const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  app.get('/api/expenses', (_req, res) => {
    res.status(200).json({expenses: store.list()});
  });
  app.post('/api/expenses', (req, res) => {
    try {
      res.status(201).json({expense: store.create(req.body)});
    } catch (error) {
      res.status(400).json({error: error.message});
    }
  });
  app.delete('/api/expenses/:id', (req, res) => {
    res.status(200).json({deleted: store.delete(req.params.id)});
  });
  app.get('/api/summary', (_req, res) => {
    res.status(200).json(processor({expenses: store.list()}));
  });
  return app;
}
