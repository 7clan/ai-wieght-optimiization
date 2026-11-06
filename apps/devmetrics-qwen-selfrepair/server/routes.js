const express = require('express');
function createApp(store, processor) {
    const app = express();
    app.use(express.json());
    app.get('/api/health', (req, res) => {
        res.json({ ok: true });
    });
    app.post('/api/entries', (req, res) => {
        const entry = req.body;
        if (!entry.project || !entry.minutes || !entry.date) {
            return res.status(400).json({ error: 'Invalid entry' });
        }
        const project = store.create(entry);
        res.status(201).json({ item: project });
    });
    app.delete('/api/entries/:id', (req, res) => {
        store.delete(req.params.id);
        res.json({ deleted: true });
    });
    app.get('/api/projects', (req, res) => {
        const projects = store.list().map((project) => {
            return { id: project.id, name: project.project };
        });
        res.json({ projects });
    });
    app.get('/api/summary', (req, res) => {
        res.json(processor({ entries: store.list() }));
    });
    return app;
}