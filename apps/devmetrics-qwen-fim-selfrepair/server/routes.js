const express = require('express');
function createApp(store, processor) {
    const app = express();
    app.use(express.json());
    app.get('/api/health', function(req, res) {
        res.json({ok: true});
    });
    app.get('/api/entries', function(req, res) {
        return res.json({entries: store.list()});
    });
    app.post('/api/entries', function(req, res) {
        try {
            const entry = req.body;
            if (!entry.project) {
                throw new Error('Project is missing');
            }
            if (!entry.minutes) {
                throw new Error('Minutes is missing');
            }
            if (!entry.date) {
                throw new Error('Date is missing');
            }
            if (!entry.note) {
                throw new Error('Note is missing');
            }
            const project = store.create(entry);
            return res.json({item: project});
        } catch (e) {
            return res.status(400).json({error: e.message});
        }
    });
    app.delete('/api/entries/:id', function(req, res) {
        const id = req.params.id;
        const project = store.delete(id);
        if (!project) {
            return res.status(400).json({error: 'Invalid entry'});
        }
        return res.json({deleted: true});
    });
    app.get('/api/projects', function(req, res) {
        const projects = Array.from(new Set(store.list()));
        projects.sort();
        return res.json({projects});
    });
    app.get('/api/summary', function(req, res) {
        return res.json(processor({entries: store.list()}));
    });
    return app;
}
module.exports = createApp;