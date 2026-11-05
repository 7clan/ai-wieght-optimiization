const React = require('react');
const {useEffect, useState} = React;
// Model-generated TaskItem JSX below. Parent App and its event wiring are trusted.
function TaskItem({task,onToggle,onDelete}) {
  return (<li className="task-row">{task.title}{' '}
    <button onClick={()=>onToggle(task.id)}>{task.done?'Un':'Done'}</button>
    <button onClick={()=>onDelete(task.id)}>Delete</button></li>);
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
