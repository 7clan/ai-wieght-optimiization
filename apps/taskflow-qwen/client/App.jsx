const React = require('react');
function App() {
  const DEMO_PROJECTS = [{ id: 'p1', name: 'Website Redesign', createdAt: '2026-11-07' }];
  const DEMO_TASKS = [{ id: 't1', projectId: 'p1', title: 'Draft homepage', priority: 'high', status: 'done', createdAt: '2026-11-07' }, { id: 't2', projectId: 'p1', title: 'Review colors', priority: 'low', status: 'todo', createdAt: '2026-11-07' }];
  const [projects, setProjects] = React.useState(DEMO_PROJECTS);
  const [selectedId, setSelectedId] = React.useState(null);
  const [tasks, setTasks] = React.useState(DEMO_TASKS);
  const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
  const [offline, setOffline] = React.useState(false);
  React.useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/projects');
        if (!res.ok) throw Error('bad');
        const data = await res.json();
        setProjects(data.projects || []);
      } catch (e) { setOffline(true); }
    })();
  }, []);
  React.useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/tasks');
        if (!res.ok) throw Error('bad');
        const data = await res.json();
        setTasks(data.tasks || []);
      } catch (e) { setOffline(true); }
    })();
  }, []);
  async function api(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw Error('request failed');
    return res.json();
  }

// Your own accepted TaskFlow code so far:
//   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
//   const [selectedId, setSelectedId] = React.useState(null);
//   const [tasks, setTasks] = React.useState(DEMO_TASKS);
//   const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
//   const [offline, setOffline] = React.useState(false);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/projects');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setProjects(data.projects || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/tasks');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setTasks(data.tasks || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//   const form = React.useRef(null);
//   const handleForm = () => {
//     api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.current.project) });
//     api('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectId: selectedId, title: form.current.title, priority: form.current.priority }) });
//     form.current.project = '';
//     form.current.title = '';
//     form.current.priority = 'medium';
//   };
//   return (
//     <div>
//       <form ref={form}>
//         <label htmlFor='project'>Project</label>
//         <input id='project' type='text' name='project' value={form.project} onChange={e => setForm({ ...form, project: e.target.value })} />
//         <label htmlFor='title'>Title</label>
//         <input id='title' type='text' name='title' value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
//         <label htmlFor='priority'>Priority</label>
//         <select id='priority' name='priority' value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
//           <option value='low'>Low</option>
//           <option value='medium'>Medium</option>
//           <option value='high'>High</option>
//         </select>
//       </form>
//       <button onClick={handleForm}>Create</button>
//       <ul>
//         {projects.map(project => (
//           <li key={project.id}>
//             <span>{project.name}</span>
//             <button onClick={() => setSelectedId(project.id)}>Select</button>
//           </li>
//         ))}
//       </ul>
//       {selectedId ? (
//         <ul>
//           <li>{tasks[selectedId].title}</li>
//           <li>{tasks[selectedId].priority}</li>
//         </ul>
//       ) : null}
//     </div>
//   );

  function api(url, opts) {
    return fetch(url, opts).then(res => res.json());
  }

  function handleForm() {
    api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form.current) }).then(() => {
      api('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ projectId: selectedId, title: form.current.title, priority: form.current.priority }) });
      form.current.project = '';
      form.current.title = '';
      form.current.priority = 'medium';
    });
  }

// Your own accepted TaskFlow code so far:
//   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
//   const [selectedId, setSelectedId] = React.useState(null);
  async function addProject(e) {
    e.preventDefault();
    if (!form.project) return;
    if (offline) return;
    try {
      const res = await api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.project }) });
      const data = await api('/api/projects');
      setProjects(data.projects || []);
      setForm({ ...form, project: '' });
    } catch (e2) { setOffline(true); }
  }
  async function addTask(e) {
    e.preventDefault();
    if (!form.title) return;
    if (offline) {
      setTasks([...tasks, { id: 'd' + (tasks.length + 1),
        projectId: selectedId, title: form.title,
        priority: form.priority, status: 'todo',
        createdAt: '2026-11-07' }]);
      setForm({ ...form, title: '' });
      return;
    }
    try {
      await api('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body:
        JSON.stringify({ projectId: selectedId, title: form.title, priority: form.priority }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
      setForm({ ...form, title: '' });
    } catch (e2) { setOffline(true); }
  }

// Add a submit handler to the form. When the form is submitted, add a new
// task to the list. Add a task to the list.
//   <form onSubmit={e => {e.preventDefault(); addTask(e)}}>
  async function toggle(t) {
    const next = t.status === 'done' ? 'todo' : 'done';
    if (offline) {
      setTasks(tasks.map(x => x.id === t.id ? { ...x, status: next } : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }

// Create the toggle function (with proper doc comments).
//   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
//   const [selectedId, setSelectedId] = React.useState(null);
//   const [tasks, setTasks] = React.useState(DEMO_TASKS);
//   const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
//   const [offline, setOffline] = React.useState(false);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/projects');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setProjects(data.projects || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/tasks');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setTasks(data.tasks || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//   const form = React.useRef(null);
//   const handleForm = () => {
//     api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body:
// JSON.stringify(form.current.project) });
//     api('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body:
// JSON.stringify({ projectId: selectedId, title: form.current.title, priority: form.current.priority }) });
//     form.current.project = '';
//     form.current.title = '';
//     form.current.priority = 'medium';
//   };
//   return (
//     <div>
//       <form ref={form} onSubmit={e => {e.preventDefault(); ...}} >
//         <input ref={form.current.project} type='text' />
//         <input ref={form.current.title} type='text' />
//         <input ref={form.current.priority} type='text' />
//         <button type='submit'>add</button>
//       </form>
//       <button onClick={toggle}>toggle</button>
//     </div>
//   );
// }
// The toggle handler (with proper doc comments) now renders an input
// for each field. In a real app, you'd want to read and validate the
// input here and then send the new value to the API.
// Now you can add a toggle button and toggle the project status with
// the help of the form ref.
// The toggle handler now renders an input for each field. In a real app,
// you'd want to read and validate the input here and then send the new
// value to the API.
// Now you can add a toggle button and toggle the project status with
// the help of the form ref.

// Create the toggle function (with proper doc comments).
//   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
//   const [selectedId, setSelectedId] = React.useState(null);
//   const [tasks, setTasks] = React.useState(DEMO_TASKS);
//   const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
//   const [offline, setOffline] = React.useState(false);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/projects');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setProjects(data.projects || []);
//       } catch (e) { set
  async function editTask(t) {
    const title = prompt('New title');
    if (!title) return;
    if (offline) {
      setTasks(tasks.map(x => x.id === t.id ? { ...x, title } : x));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }) });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }

// Your own accepted App code so far:
//   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
//   const [selectedId, setSelectedId] = React.useState(null);
//   const [tasks, setTasks] = React.useState(DEMO_TASKS);
//   const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
//   const [offline, setOffline] = React.useState(false);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/projects');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setProjects(data.projects || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//   React.useEffect(() => {
//     (async () => {
//       try {
//         const res = await fetch('/api/tasks');
//         if (!res.ok) throw Error('bad');
//         const data = await res.json();
//         setTasks(data.tasks || []);
//       } catch (e) { setOffline(true); }
//     })();
//   }, []);
//     const res = await fetch(url, opts);
//     if (!res.ok) throw Error('request failed');
//     return res.json();
//   }
//
// // Your own accepted TaskFlow code so far:
// //   const [projects, setProjects] = React.useState(DEMO_PROJECTS);
// //   const [selectedId, setSelectedId] = React.useState(null);
// //   const [tasks, setTasks] = React.useState(DEMO_TASKS);
// //   const [form, setForm] = React.useState({ project: '', title: '', priority: 'medium' });
// //   const [offline, setOffline] = React.useState(false);
// //   React.useEffect(() => {
// //     (async () => {
// //       try {
// //         const res = await fetch('/api/projects');
// //         if (!res.ok) throw Error('bad');
// //         const data = await res.json();
// //         setProjects(data.projects || []);
// //       } catch (e) { setOffline(true); }
// //     })();
// //   }, []);
// //   React.useEffect(() => {
// //     (async () => {
// //       try {
// //         const res = await fetch('/api/tasks');
// //         if (!res.ok) throw Error('bad');
// //         const data = await res.json();
// //         setTasks(data.tasks || []);
// //       } catch (e) { setOffline(true); }
// //     })();
// //   }, []);
// //   const form = React.useRef(null);
// //   const handleForm = () => {
// //     api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body:
// JSON.stringify(form.current.project) });
// //     api('/api/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body:
// JSON.stringify({ projectId: selectedId, title: form.current.title, priority: form.current.priority })
// });
// //     form.current.project = '';
// //     form.current.title = '';
// //     form.current.priority = 'medium';
// //   };
// //   return (
// //     <div>
// //       <form ref={form} onSubmit={e => {e.preventDefault(); ...}}>
// //         <input
// //           ref={form.current.project}
// //           type="text"
// //           placeholder="Project..."
// //           value={form.current.project}
// //           onChange={e => setForm({...form, project: e.target.value})}
// //         />
// //         <input
// //           ref={form.current.title}
// //           type="text"
  async function removeTask(t) {
    if (offline) {
      setTasks(tasks.filter(x => x.id !== t.id));
      return;
    }
    try {
      await api('/api/tasks/' + t.id, { method: 'DELETE' });
      const data = await api('/api/tasks?projectId=' + selectedId);
      setTasks(data.tasks || []);
    } catch (e2) { setOffline(true); }
  }

// The fetch function and useEffect have been imported for you. They are
// built-in, and you can import from React.
// The code you need is below.

// You can copy and paste the code from the react module.
// You can see the code you need in the console.
  const shown = offline ? DEMO_TASKS : tasks;
  const doneCount = shown.filter(t => t.status === 'done').length;
  const pct = shown.length ? Math.round(100 * doneCount / shown.length) : 0;
  return (
    <div className="app">
      <aside className="sidebar">
        {offline && <div className="offline-badge">offline</div>}
        {(offline ? DEMO_PROJECTS : projects).map(p => (
          <button key={p.id} className="project-btn"
            onClick={() => setSelectedId(p.id)}>{p.name}</button>
        ))}
        <form className="add-form" onSubmit={addProject}>
          <input value={form.project}
            onChange={e => setForm({ ...form, project: e.target.value })}
            placeholder="New project" />
          <button type="submit">Add project</button>
        </form>
      </aside>
      <main>
        <div className="progress">{pct}% ({doneCount}/{shown.length})</div>
        <form className="add-form" onSubmit={addTask}>
          <input value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="New task" />
          <select value={form.priority}
            onChange={e => setForm({ ...form, priority: e.target.value })}>
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
