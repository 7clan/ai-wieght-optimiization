const { useState, useEffect } = require('react');
const DEMO_PROJECTS = [{id:"p1", name:"Website Redesign", createdAt:"2026-11-07"}];
const DEMO_TASKS = [{id:"t1", projectId:"p1", title:"Draft homepage",
  priority:"high", status:"done", createdAt:"2026-11-07"},
  {id:"t2", projectId:"p1", title:"Review colors",
  priority:"low", status:"todo", createdAt:"2026-11-07"}];
function App() {
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [form, setForm] = useState({project: "", title: "", priority: "medium"});
  const [offline, setOffline] = useState(false);
  const [demoTasks, setDemoTasks] = useState(DEMO_TASKS);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/projects');
        if (!res.ok) throw Error('bad');
        const data = await res.json();
        setProjects(data.projects || []);
        if (data.projects && data.projects[0]) setSelectedId(data.projects[0].id);
      } catch (e) { setOffline(true); }
    })();
  }, []);
  useEffect(() => {
    if (!offline || !selectedId) return;
  }, [selectedId, offline]);
  const shown = offline ? demoTasks : tasks;
  const done = shown.filter(t => t.status === 'done').length;
  const pct = shown.length ? Math.round(100 * done / shown.length) : 0;
  async function api(url, opts) {
    if (offline) return null;
    const res = await fetch(url, opts);
    if (!res.ok) throw Error('request failed');
    return res.json();
  }
  async function addProject(e) {
    e.preventDefault();
    if (!form.project) return;
    if (offline) return;
    try {
      await api('/api/projects', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: form.project})});
      const res = await fetch('/api/projects');
      const data = await res.json();
      setProjects(data.projects || []);
    } catch (e) { setOffline(true); }
  }
  async function addTask(e) {
    e.preventDefault();
    if (!form.title) return;
    if (offline) {
      setDemoTasks([...demoTasks, {id: 'd' + (demoTasks.length + 1),
        projectId: selectedId, title: form.title, priority: form.priority,
        status: 'todo', createdAt: '2026-11-07'}]);
      setForm({...form, title: ''});
      return;
    }
    try {
      await api('/api/tasks', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({projectId: selectedId, title: form.title,
          priority: form.priority})});
      const res = await fetch('/api/tasks?projectId=' + selectedId);
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (e) { setOffline(true); }
  }
  async function toggle(t) {
    const next = t.status === 'done' ? 'todo' : 'done';
    if (offline) {
      setDemoTasks(demoTasks.map(x => x.id === t.id ? {...x, status: next} : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: next})});
      const res = await fetch('/api/tasks?projectId=' + selectedId);
      setTasks((await res.json()).tasks || []);
    } catch (e) { setOffline(true); }
  }
  async function editTask(t) {
    const title = prompt('New title');
    if (!title) return;
    if (offline) {
      setDemoTasks(demoTasks.map(x => x.id === t.id ? {...x, title} : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title})});
      const res = await fetch('/api/tasks?projectId=' + selectedId);
      setTasks((await res.json()).tasks || []);
    } catch (e) { setOffline(true); }
  }
  async function removeTask(t) {
    if (offline) {
      setDemoTasks(demoTasks.filter(x => x.id !== t.id));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, {method: 'DELETE'});
      const res = await fetch('/api/tasks?projectId=' + selectedId);
      setTasks((await res.json()).tasks || []);
    } catch (e) { setOffline(true); }
  }
  const projs = offline ? DEMO_PROJECTS : projects;
  return (
    <div className="app">
      <aside className="sidebar">
        {offline && <div className="offline-badge">offline</div>}
        {projs.map(p => (
          <button key={p.id} className="project-btn"
            onClick={() => setSelectedId(p.id)}>{p.name}</button>
        ))}
        <form className="add-form" onSubmit={addProject}>
          <input value={form.project}
            onChange={e => setForm({...form, project: e.target.value})}
            placeholder="New project" />
          <button type="submit">Add project</button>
        </form>
      </aside>
      <main>
        <div className="progress">{pct}% ({done}/{shown.length})</div>
        <form className="add-form" onSubmit={addTask}>
          <input value={form.title}
            onChange={e => setForm({...form, title: e.target.value})}
            placeholder="New task" />
          <select value={form.priority}
            onChange={e => setForm({...form, priority: e.target.value})}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
          <button type="submit">Add task</button>
        </form>
        <div>
          <button className="filter-all">All</button>
          <button className="filter-todo">Todo</button>
          <button className="filter-doing">Doing</button>
          <button className="filter-done">Done</button>
          <input className="search" placeholder="Search" />
        </div>
        {shown.map(t => (
          <div key={t.id} className="task-row">
            <span>{t.title}</span>
            <span className={'priority-' + t.priority}>{t.priority}</span>
            <button className="toggle" onClick={() => toggle(t)}>
              {t.status === 'done' ? 'undo' : 'done'}</button>
            <button className="edit" onClick={() => editTask(t)}>edit</button>
            <button className="delete" onClick={() => removeTask(t)}>delete</button>
          </div>
        ))}
      </main>
    </div>
  );
}
module.exports = App;
