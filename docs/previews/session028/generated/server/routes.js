// Build PocketLedger: a small personal expense tracker. This is a NEW
// application, not FocusBoard. Users can add expenses, browse and remove them,
// and see category totals. Use React, Express and Python 3.11, plus an on-disk
// JSON store in Node.js. Implement the actual application code in five modules.
// There is no task-completion or status-toggle feature.
// 
// Expense fields: id (string), description (nonempty string),
// amount_cents (positive integer), category (food, travel or other).
// 
// API:
//   GET /api/expenses           -> HTTP 200 {expenses:[...]}
//   POST /api/expenses          -> HTTP 201 {expense:{id,description,amount_cents,category}}
//   DELETE /api/expenses/:id    -> HTTP 200 {deleted:boolean}
//   GET /api/summary            -> HTTP 200 {count:int,total_cents:int,by_category:object}
// 
// Server/store.js exposes createStore(filePath). Its returned object implements
// list(), create(body), delete(id). It MUST persist across a fresh createStore()
// call with the same filePath. Store writes to the provided filePath only;
// use require('node:fs') and no other dependencies. On invalid description or
// amount_cents reject with Error.
// 
// Server/routes.js exposes createApp(store, processor), returning an Express app.
// processor({expenses:store.list()}) returns the Python summary object. Use
// require('express') only, express.json() and the exact response envelopes above.
// 
// Backend/logic.py defines transform(payload). It returns {count,total_cents,
// by_category}, where by_category sums integer amount_cents by category, and
// count is the expense count. Empty input returns count=0, total_cents=0 and
// by_category={}. No external Python modules.
// 
// Client/App.jsx defines React function App, uses fetch for GET/POST/DELETE,
// and displays a heading with PocketLedger, description and amount inputs,
// Add expense button, expenses list, delete controls and a category summary.
// No external UI libraries. CSS is responsive, valid and self-contained.
// server/routes.js; implement ALL four endpoints.
const express = require('express');
function createApp(store, processor) {
    const app = express();
    const id = req.params.id;
    if (store.delete(id)) {
        res.status(200).json({ deleted: true });
    }
    else {
        res.status(404).json({ error: 'Expense not found' });
    }
}
app.get('/api/expenses', (req, res) => {
    const expenses = processor(store.list());
    res.json(expenses);
});
app.post('/api/expenses', (req, res) => {
    const { id, description, amount_cents, category } = req.body;
    if (store.create({ id, description, amount_cents, category })) {
        res.status(201).json({ expense: { id, description, amount_cents, category } });
    }
    else {
        res.status(400).json({ error: 'Expense creation failed' });
    }
});
app.delete('/api/expenses/:id', (req, res) => {
    const id = req.params.id;
    const deleted = store.delete(id);
    if (deleted) {
        res.status(200).json({ deleted: true });
    }
    else {
        res.status(404).json({ error: 'Expense not found' });
    }
});
app.get('/api/summary', (req, res) => {
    const summary = processor(store.list());
    res.json(summary);
});
app.listen(3000, () => console.log('Server running on port 3000'));