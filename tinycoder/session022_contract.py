"""Session022 frozen FIM slots. Surrounding code is trusted scaffolding, not model output."""
from __future__ import annotations

from .session021_contract import PUBLIC, holdout, spec_hash

SLOTS = (
    'logic_completed', 'api_get', 'api_post', 'api_patch',
    'api_delete', 'api_summary', 'ui_card', 'css_theme',
)

# The templates are deliberately short: model source occupies only marked
# insertion points. Code outside insertion points is NOT attributed to Qwen.
TEMPLATES = {
    'logic': '''def transform(payload):
    tasks = payload.get('tasks', [])
    total = len(tasks)
    # Count tasks where done is true.
    completed = [[logic_completed]]
    return {'total': total, 'completed': completed, 'remaining': total - completed}
''',
    'api': '''const express = require('express');
function createApp(store, processor) {
  const app = express();
  app.use(express.json());
  // GET all tasks, response {tasks:[...]}
  app.get('/api/tasks', (req, res) => res.json([[api_get]]));
  // POST a new task, response {task:{...}}
  app.post('/api/tasks', (req, res) => res.status(201).json([[api_post]]));
  // PATCH /api/tasks/:id, response {task:{...}}
  app.patch('/api/tasks/:id', (req, res) => res.json([[api_patch]]));
  // DELETE /api/tasks/:id, response {deleted:boolean}
  app.delete('/api/tasks/:id', (req, res) => res.json([[api_delete]]));
  // GET /api/summary, call processor({tasks:store.list()})
  app.get('/api/summary', (req, res) => res.json([[api_summary]]));
  return app;
}
''',
    'ui': '''const React = require('react');
const {useEffect, useState} = React;
// Model-generated TaskItem JSX below. Parent App and its event wiring are trusted.
function TaskItem({task,onToggle,onDelete}) {
  return (<li className="task-row">[[ui_card]]</li>);
}
function App() {
  const [tasks, setTasks] = useState([]);
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('medium');
  const [summary, setSummary] = useState({total:0,completed:0,remaining:0});
  const [error, setError] = useState('');
  async function refresh() {
    try {
      const [items, stats] = await Promise.all([fetch('/api/tasks'),fetch('/api/summary')]);
      if (!items.ok || !stats.ok) throw Error('Cannot load task data');
      setTasks((await items.json()).tasks);
      setSummary(await stats.json());
      setError('');
    } catch (e) { setError(String(e.message||e)); }
  }
  useEffect(()=>{refresh();},[]);
  async function mutate(url, method, body) {
    try {
      const response=await fetch(url,{method,headers:{'Content-Type':'application/json'},
        ...(body?{body:JSON.stringify(body)}:{})});
      if(!response.ok) throw Error('Action failed: '+response.status);
      await refresh();
    } catch(e){setError(String(e.message||e));}
  }
  async function create(e) {
    e.preventDefault();
    if(!title.trim())return;
    await mutate('/api/tasks','POST',{title:title.trim(),priority});
    setTitle('');
  }
  return <main className="board"><header><div className="brand">◆ FOCUSBOARD</div>
    <h1>Your tasks, in focus.</h1><p>Plan, prioritize, and finish what matters.</p></header>
    <section className="stats" aria-label="Task statistics">
      <article><b>{summary.total}</b><span>Total tasks</span></article>
      <article><b>{summary.completed}</b><span>Completed</span></article>
      <article><b>{summary.remaining}</b><span>Remaining</span></article>
    </section>
    <form onSubmit={create}><input aria-label="New task title" value={title}
      onChange={e=>setTitle(e.target.value)} placeholder="What needs to be done?" required />
      <select aria-label="Priority" value={priority} onChange={e=>setPriority(e.target.value)}>
        <option value="low">Low</option><option value="medium">Medium</option>
        <option value="high">High</option></select><button type="submit">Add task</button></form>
    {error?<p role="alert">{error}</p>:null}
    <h2>Task board</h2>
    {tasks.length?<ul className="tasks">{tasks.map(t=><TaskItem key={t.id} task={t}
      onToggle={()=>mutate('/api/tasks/'+t.id,'PATCH',{done:!t.done})}
      onDelete={()=>mutate('/api/tasks/'+t.id,'DELETE')} />)}</ul>:
      <div className="empty">Your next big idea starts here. Add your first task above.</div>}
    </main>;
}
module.exports = App;
''',
    'css': '''/* FocusBoard: trusted layout defaults plus Qwen generated theme rules. */
*{box-sizing:border-box}body{margin:0;background:#f4f6fc;color:#172341;
font-family:ui-sans-serif,system-ui,Arial,sans-serif}.board{max-width:1050px;margin:0 auto;padding:58px 24px}
header{margin-bottom:30px}.brand{font-size:12px;font-weight:800;letter-spacing:.2em;color:#6178dd}
h1{font-size:clamp(35px,5vw,56px);letter-spacing:-.04em;margin:13px 0}
p{color:#7080a2}h2{margin-top:35px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.stats article{background:white;padding:25px;border:1px solid #e0e6f1;border-radius:18px;display:grid}
.stats b{font-size:36px}.stats span{color:#7a89a7;font-size:13px}
form{display:flex;gap:12px;margin-top:30px}input,select,button{padding:14px;border:1px solid #d4ddef;border-radius:11px}
input{flex:1;min-width:0}button{background:#6076e9;color:white;cursor:pointer;font-weight:700}
.tasks{list-style:none;padding:0}.task-row{margin:10px 0;background:white;border:1px solid #e0e6f1;
padding:18px;border-radius:12px;display:flex;align-items:center;gap:12px}
.task-row button{padding:8px 12px}.empty{background:white;padding:60px;text-align:center;border-radius:15px;color:#7f8ba6}
@media(max-width:650px){.stats{grid-template-columns:1fr}form{flex-wrap:wrap}input{flex-basis:100%}}
/* Begin model-generated CSS theme. */
[[css_theme]]
''',
}

SLOT_TO_ROLE = {s: ('logic' if s.startswith('logic') else 'api' if s.startswith('api')
                    else 'ui' if s.startswith('ui') else 'css') for s in SLOTS}


def assemble(slots):
    import re
    outputs = {}
    for role, template in TEMPLATES.items():
        result = template
        for name in re.findall(r'\[\[([a-z_]+)\]\]', template):
            result = result.replace('[['+name+']]', slots.get(name, ''))
        outputs[role] = result
    return outputs


def public_cases():
    return PUBLIC


def holdout_cases():
    return holdout()
