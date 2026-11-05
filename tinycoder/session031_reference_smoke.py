"""Trusted reference DevMetrics implementation: positive control only.

Hand-authored calibration code proving every Session031 check can pass.
Never enters model prompts and is never attributed to Qwen.
"""
from __future__ import annotations

import json
from pathlib import Path

from .session031 import evaluate
from .session031_contract import PUBLIC, holdout


REFERENCE = {
"logic": '''    entries = payload.get('entries', [])
    by_project = {}
    by_day = {}
    for e in entries:
        p = e['project']
        d = e['date']
        by_project[p] = by_project.get(p, 0) + e['minutes']
        by_day[d] = by_day.get(d, 0) + e['minutes']
    total = sum(e['minutes'] for e in entries)
    busiest = None
    best = -1
    for d in sorted(by_day):
        if by_day[d] > best:
            best = by_day[d]
            busiest = d
    return {'total_minutes': total, 'by_project': by_project, 'by_day': by_day,
            'active_projects': len(by_project), 'busiest_day': busiest}
''',
"store": '''  const file = filePath;
  function read() {
    try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
    catch (e) { return []; }
  }
  function write(rows) { fs.writeFileSync(file, JSON.stringify(rows, null, 2)); }
  function createStoreInstance() {
    let rows = read();
    return {
      list: () => rows.map((x) => ({ ...x })),
      create: (body) => {
        if (!body || typeof body.project !== 'string' || !body.project ||
            !Number.isInteger(body.minutes) || body.minutes <= 0 ||
            !/^\\d{4}-\\d{2}-\\d{2}$/.test(String(body.date || '')))
          throw Error('Invalid entry');
        const entry = { id: 'e' + (rows.length + 1) + '-' + Date.now(),
          project: body.project, minutes: body.minutes, date: body.date,
          note: typeof body.note === 'string' ? body.note : '' };
        rows = rows.concat([entry]);
        write(rows);
        return { ...entry };
      },
      delete: (id) => {
        const before = rows.length;
        rows = rows.filter((x) => x.id !== String(id));
        write(rows);
        return rows.length < before;
      }
    };
  }
  return createStoreInstance();
}
''',
"api": '''  const app = express();
  app.use(express.json());
  app.get('/api/health', (req, res) => res.json({ ok: true }));
  app.get('/api/entries', (req, res) => res.json({ entries: store.list() }));
  app.post('/api/entries', (req, res) => {
    try {
      const item = store.create(req.body);
      res.status(201).json({ item });
    } catch (err) {
      res.status(400).json({ error: 'Invalid entry' });
    }
  });
  app.delete('/api/entries/:id', (req, res) =>
    res.json({ deleted: store.delete(req.params.id) }));
  app.get('/api/projects', (req, res) => {
    const names = [...new Set(store.list().map((x) => x.project))].sort();
    res.json({ projects: names });
  });
  app.get('/api/summary', (req, res) =>
    res.json(processor({ entries: store.list() })));
  return app;
}
''',
"ui": '''  const [entries, setEntries] = React.useState([]);
  const [summary, setSummary] = React.useState(null);
  const [offline, setOffline] = React.useState(false);
  const [filter, setFilter] = React.useState('');
  const [form, setForm] = React.useState({ project: '', minutes: '', date: '', note: '' });
  const demoEntries = [
    { project: 'api-server', minutes: 95, date: '2026-11-03', note: 'routes' },
    { project: 'mobile-ui', minutes: 140, date: '2026-11-04', note: 'screens' },
    { project: 'docs', minutes: 60, date: '2026-11-04', note: 'guide' }
  ];
  function summarizeJs(list) {
    const byProject = {}; const byDay = {}; let total = 0;
    list.forEach((e) => {
      total += e.minutes;
      byProject[e.project] = (byProject[e.project] || 0) + e.minutes;
      byDay[e.date] = (byDay[e.date] || 0) + e.minutes;
    });
    let busiest = null; let best = -1;
    Object.keys(byDay).sort().forEach((d) => {
      if (byDay[d] > best) { best = byDay[d]; busiest = d; }
    });
    return { total_minutes: total, by_project: byProject, by_day: byDay,
      active_projects: Object.keys(byProject).length, busiest_day: busiest };
  }
  const load = async () => {
    try {
      const r1 = await fetch('/api/entries');
      if (!r1.ok) throw Error('bad status');
      const d1 = await r1.json();
      const r2 = await fetch('/api/summary');
      if (!r2.ok) throw Error('bad status');
      const d2 = await r2.json();
      setEntries(d1.entries || []);
      setSummary(d2);
      setOffline(false);
    } catch (err) {
      setEntries(demoEntries);
      setSummary(summarizeJs(demoEntries));
      setOffline(true);
    }
  };
  React.useEffect(() => { load(); }, []);
  const shown = entries.filter((e) => !filter || e.project === filter);
  const projects = [...new Set(entries.map((e) => e.project))].sort();
  const submit = async (ev) => {
    ev.preventDefault();
    try {
      await fetch('/api/entries', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: form.project, minutes: Number(form.minutes),
          date: form.date, note: form.note }) });
    } catch (err) { /* offline */ }
    load();
  };
  const remove = async (id) => {
    try { await fetch('/api/entries/' + id, { method: 'DELETE' }); }
    catch (err) { /* offline */ }
    load();
  };
  return (
    <div className="wrap">
      <h1>DevMetrics</h1>
      {offline
        ? <span className="badge offline">offline demo mode</span>
        : <span className="badge online">online</span>}
      <section className="cards">
        <div className="card"><span className="label">total minutes</span>
          <strong>{summary ? summary.total_minutes : 0}</strong></div>
        <div className="card"><span className="label">active projects</span>
          <strong>{summary ? summary.active_projects : 0}</strong></div>
        <div className="card"><span className="label">busiest day</span>
          <strong>{summary && summary.busiest_day ? summary.busiest_day : '-'}</strong></div>
      </section>
      <form onSubmit={submit}>
        <input value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })} placeholder="project" />
        <input value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })} placeholder="minutes" />
        <input value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} placeholder="date" />
        <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="note" />
        <button>Add entry</button>
      </form>
      <label>project filter
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">all</option>
          {projects.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <ul className="entries">
        {shown.map((e) => (
          <li key={e.id || e.project + e.date}>
            <span>{e.project}</span><span>{e.minutes} min</span>
            <span>{e.date}</span><span>{e.note}</span>
            <button onClick={() => remove(e.id)}>Delete</button>
          </li>
        ))}
      </ul>
      <section className="breakdown">
        <h2>by project</h2>
        <ul>
          {summary ? Object.keys(summary.by_project).map((p) => (
            <li key={p}>{p}: {summary.by_project[p]}</li>)) : null}
        </ul>
      </section>
    </div>
  );
}
module.exports = App;
''',
"css": '''  background: #0d1527;
  color: #e8eefb;
  font: 15px/1.5 system-ui, sans-serif;
  margin: 0;
}
.wrap { max-width: 1000px; margin: 0 auto; padding: 32px 20px; }
h1 { letter-spacing: -0.03em; margin: 8px 0 16px; }
.badge { border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 700; }
.badge.offline { background: #67354b; color: #ffd6e1; }
.badge.online { background: #165440; color: #b5ffdd; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; }
.card { background: #182a46; border: 1px solid #33507a; border-radius: 12px;
  padding: 14px 18px; min-width: 140px; }
.card .label { display: block; font-size: 11px; color: #9db2d6; }
.card strong { font-size: 26px; }
form { display: flex; gap: 8px; flex-wrap: wrap; margin: 18px 0; }
input, select { background: #101d33; border: 1px solid #33507a; color: #e8eefb;
  border-radius: 8px; padding: 9px 11px; }
button { background: #2c6fed; border: 0; color: white; border-radius: 8px;
  padding: 9px 14px; font-weight: 700; cursor: pointer; }
.entries { list-style: none; padding: 0; display: grid; gap: 8px; }
.entries li { background: #182a46; border: 1px solid #33507a; border-radius: 10px;
  padding: 10px 14px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.entries button { background: #a03546; }
@media (max-width: 640px) { .cards, form { flex-direction: column; } }
''',
}

REF_PATH = Path(__file__).with_suffix(".reference.json")


def reference_modules():
    prefix = {
        "logic": "def summarize(payload):\n",
        "store": "const fs = require('node:fs');\nfunction createStore(filePath) {\n",
        "api": "const express = require('express');\nfunction createApp(store, processor) {\n",
        "ui": "const React = require('react');\nfunction App() {\n",
        "css": "body {\n",
    }
    return {role: prefix[role] + REFERENCE[role] for role in REFERENCE}


def main():
    for phase, cases in (("public", PUBLIC), ("holdout", holdout())):
        report = evaluate(reference_modules(), cases, phase)
        if not report["integrated"]:
            raise RuntimeError(
                "Session031 positive control failed (%s): %s"
                % (phase, report["failure_reasons"]))
        print("PASS: trusted reference passes every %s check inside Docker" % phase,
              flush=True)
    REF_PATH.write_text(json.dumps(reference_modules(), indent=1), encoding="utf8")


if __name__ == "__main__":
    main()
