import React,{useEffect,useMemo,useState} from 'react';

const STATUSES=[['todo','To do'],['doing','In progress'],['done','Completed']];
const COLORS=['#7297ff','#a38cff','#54c5ad','#ef9b74','#ee769d'];
const DISPLAY={low:'Low',medium:'Medium',high:'High'};

async function api(route,method='GET',body){
  const response=await fetch('/api/'+route,{method,headers:{'Content-Type':'application/json'},
    ...(body?{body:JSON.stringify(body)}:{})});
  const json=await response.json();
  if(!response.ok)throw Error(json.error||'Request failed');
  return json.data;
}
function Symbol({name,size=19}){
  const paths={
    grid:<><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
    plus:<path d="M12 5v14M5 12h14"/>,
    search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v5m10-5v5M3 10h18"/></>,
    dots:<><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
    check:<path d="m4 12 5 5L20 6"/>,
    bolt:<path d="m13 2-9 12h7l-1 8 10-13h-7z"/>,
    layers:<><path d="m12 2 10 6-10 6L2 8z"/><path d="m2 12 10 6 10-6M2 16l10 6 10-6"/></>,
    close:<path d="M5 5l14 14M19 5 5 19"/>,
    trash:<><path d="M4 7h16M10 4h4M7 7l1 14h8l1-14"/><path d="M10 11v6m4-6v6"/></>
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.grid}</svg>;
}

export default function App(){
  const [projects,setProjects]=useState([]),[tasks,setTasks]=useState([]);
  const [active,setActive]=useState('all'),[loading,setLoading]=useState(true);
  const [error,setError]=useState(''),[message,setMessage]=useState('');
  const [projectModal,setProjectModal]=useState(false),[taskModal,setTaskModal]=useState(false);
  const [newProject,setNewProject]=useState({name:'',description:'',color:COLORS[0]});
  const [newTask,setNewTask]=useState({title:'',description:'',priority:'medium',due_date:''});
  const [query,setQuery]=useState('');
  async function refresh(){
    try{const data=await api('overview');setProjects(data.projects);setTasks(data.tasks);setError('');}
    catch(e){setError(e.message);}finally{setLoading(false);}
  }
  useEffect(()=>{refresh();},[]);
  useEffect(()=>{if(message){const timer=setTimeout(()=>setMessage(''),3300);return()=>clearTimeout(timer);}},[message]);
  const current=projects.find(p=>p.id===active);
  const visible=useMemo(()=>tasks.filter(t=>(active==='all'||t.project_id===active)
    &&(!query||[t.title,t.description].join(' ').toLowerCase().includes(query.toLowerCase()))),[tasks,active,query]);
  const done=visible.filter(t=>t.status==='done').length;
  const inProgress=visible.filter(t=>t.status==='doing').length;
  const title=current?.name||'All projects';
  const percent=visible.length?Math.round(done/visible.length*100):0;
  async function createProject(e){
    e.preventDefault();
    try{const created=await api('projects','POST',newProject);await refresh();setActive(created.id);
      setProjectModal(false);setNewProject({name:'',description:'',color:COLORS[0]});setMessage('Project created');}
    catch(e){setError(e.message);}
  }
  async function createTask(e){
    e.preventDefault();
    const pid=current?.id||projects[0]?.id;
    if(!pid){setError('Create a project first');return;}
    try{await api('tasks','POST',{...newTask,project_id:pid,due_date:newTask.due_date||null});
      await refresh();setTaskModal(false);setNewTask({title:'',description:'',priority:'medium',due_date:''});
      setMessage('Task created');}
    catch(e){setError(e.message);}
  }
  async function changeTask(task,changes){
    try{await api('tasks/'+task.id,'PATCH',changes);await refresh();}
    catch(e){setError(e.message);}
  }
  async function removeTask(task){
    if(!window.confirm(`Delete “${task.title}”?`))return;
    try{await api('tasks/'+task.id,'DELETE');await refresh();setMessage('Task deleted');}
    catch(e){setError(e.message);}
  }
  async function removeProject(){
    if(!current||!window.confirm(`Delete “${current.name}” and all its tasks?`))return;
    try{await api('projects/'+current.id,'DELETE');setActive('all');await refresh();setMessage('Project deleted');}
    catch(e){setError(e.message);}
  }
  return <div className="shell">
    <aside className="sidebar">
      <div className="logo"><span className="logo-mark"><Symbol name="layers" size={22}/></span><span>orbit<span className="logo-period">.</span></span></div>
      <div className="workspace-label">WORKSPACE</div>
      <button className={'nav-link '+(active==='all'?'selected':'')} onClick={()=>setActive('all')}><Symbol name="grid"/> Overview <span className="nav-count">{tasks.length}</span></button>
      <div className="sidebar-section"><span>YOUR PROJECTS</span><button title="Create project" aria-label="Create project" onClick={()=>setProjectModal(true)}><Symbol name="plus" size={18}/></button></div>
      <div className="project-list">{projects.map(p=><button className={'project-link '+(active===p.id?'selected':'')} key={p.id} onClick={()=>setActive(p.id)}><span className="project-dot" style={{background:p.color}}/><span className="truncate">{p.name}</span><span className="nav-count">{tasks.filter(t=>t.project_id===p.id).length}</span></button>)}</div>
      {projects.length===0&&!loading&&<p className="sidebar-empty">Your next big idea starts here.</p>}
      <button className="new-project-link" onClick={()=>setProjectModal(true)}><Symbol name="plus" size={16}/> New project</button>
      <div className="sidebar-bottom"><div className="avatar">PM</div><div><strong>My workspace</strong><span>Local, private data</span></div><Symbol name="dots" size={17}/></div>
    </aside>
    <div className="content">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <strong>{title}</strong></div><div className="topbar-right"><span className="today"><Symbol name="calendar" size={16}/>{new Date().toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}</span><span className="avatar small-avatar">PM</span></div></header>
      <main className="main">
        {error&&<div className="alert" role="alert">{error}<button onClick={()=>setError('')} aria-label="Dismiss error"><Symbol name="close" size={16}/></button></div>}
        {message&&<div className="toast" role="status">✓ {message}</div>}
        <div className="page-intro"><div><div className="eyebrow">PROJECT WORKSPACE</div><h1>{title}<span className="title-accent">.</span></h1><p>Keep ideas moving, one task at a time.</p></div><div className="action-row">{current&&<button className="subtle-danger" onClick={removeProject} title="Delete current project"><Symbol name="trash" size={16}/></button>}<button className="primary-btn" onClick={()=>projects.length?setTaskModal(true):setProjectModal(true)}><Symbol name="plus" size={18}/>{projects.length?'New task':'New project'}</button></div></div>
        <div className="stat-grid">
          <article className="stat-card"><div className="stat-icon purple"><Symbol name="layers"/></div><div className="stat-label">Total tasks</div><div className="stat-value">{visible.length}<span className="stat-small">across your workflow</span></div></article>
          <article className="stat-card"><div className="stat-icon orange"><Symbol name="bolt"/></div><div className="stat-label">In progress</div><div className="stat-value">{inProgress}<span className="stat-small">keep the momentum</span></div></article>
          <article className="stat-card"><div className="stat-icon green"><Symbol name="check"/></div><div className="stat-label">Completed</div><div className="stat-value">{done}<span className="stat-small">great work so far</span></div></article>
          <article className="stat-card progress-card"><div className="stat-label">Overall progress</div><div className="progress-number">{percent}%</div><div className="progress-track"><div style={{width:percent+'%'}}/></div><span className="stat-small">{done} of {visible.length} tasks done</span></article>
        </div>
        <section className="board-section"><div className="board-heading"><div><h2>Your task board</h2><p>Stay focused on what matters most.</p></div><div className="board-tools"><div className="search-wrap"><Symbol name="search" size={16}/><input aria-label="Search tasks" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search tasks..."/></div></div></div>
          {loading?<div className="empty-state">Loading workspace…</div>:projects.length===0?<div className="empty-state"><span className="empty-symbol">✦</span><h3>Your workspace is waiting</h3><p>Create your first project to organize tasks and track progress.</p><button className="primary-btn" onClick={()=>setProjectModal(true)}><Symbol name="plus"/>Create a project</button></div>:
          <div className="kanban">{STATUSES.map(([status,label])=><div className="kanban-column" key={status}><div className="column-header"><span className={'status-dot '+status}/><strong>{label}</strong><span className="count">{visible.filter(t=>t.status===status).length}</span></div><div className="column-body">{visible.filter(t=>t.status===status).map(t=><article className="task-card" key={t.id}>
              <div className="task-card-top"><span className={'priority priority-'+t.priority}>{DISPLAY[t.priority]}</span><button className="icon-button" aria-label={'Delete '+t.title} title="Delete task" onClick={()=>removeTask(t)}><Symbol name="trash" size={15}/></button></div>
              <h3>{t.title}</h3>{t.description&&<p className="task-desc">{t.description}</p>}
              <div className="task-footer"><div className="task-meta">{t.due_date&&<span><Symbol name="calendar" size={14}/>{t.due_date}</span>}{active==='all'&&<span>{projects.find(p=>p.id===t.project_id)?.name||'Project'}</span>}</div><select aria-label={'Status for '+t.title} value={t.status} onChange={e=>changeTask(t,{status:e.target.value})}>{STATUSES.map(([s,l])=><option key={s} value={s}>{l}</option>)}</select></div>
              </article>)}<button className="add-card" onClick={()=>setTaskModal(true)}><Symbol name="plus" size={16}/> Add task</button></div></div>)}</div>}
        </section>
        <footer className="page-footer">Made to get things done. <span>Orbit · Full-stack demo</span></footer>
      </main>
    </div>
    {projectModal&&<div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setProjectModal(false)}><section className="dialog" role="dialog" aria-modal="true" aria-label="New project"><div className="dialog-head"><div><span className="eyebrow">START SOMETHING GREAT</span><h2>New project</h2></div><button onClick={()=>setProjectModal(false)} aria-label="Close"><Symbol name="close"/></button></div><form onSubmit={createProject}><label>Project name<input required maxLength="80" autoFocus value={newProject.name} onChange={e=>setNewProject({...newProject,name:e.target.value})} placeholder="e.g. Website redesign"/></label><label>Description<textarea maxLength="500" rows="3" value={newProject.description} onChange={e=>setNewProject({...newProject,description:e.target.value})} placeholder="What's this project about?"/></label><div className="color-chooser"><span>Project color</span><div>{COLORS.map(c=><button type="button" aria-label={'Choose '+c} aria-pressed={newProject.color===c} className={newProject.color===c?'active':''} key={c} style={{background:c}} onClick={()=>setNewProject({...newProject,color:c})}/>)}</div></div><div className="dialog-actions"><button type="button" onClick={()=>setProjectModal(false)}>Cancel</button><button className="primary-btn" type="submit">Create project</button></div></form></section></div>}
    {taskModal&&<div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setTaskModal(false)}><section className="dialog" role="dialog" aria-modal="true" aria-label="New task"><div className="dialog-head"><div><span className="eyebrow">MAKE IT HAPPEN</span><h2>New task</h2></div><button onClick={()=>setTaskModal(false)} aria-label="Close"><Symbol name="close"/></button></div><form onSubmit={createTask}><label>Task title<input required maxLength="160" autoFocus value={newTask.title} onChange={e=>setNewTask({...newTask,title:e.target.value})} placeholder="What needs to get done?"/></label><label>Details<textarea rows="3" maxLength="1000" value={newTask.description} onChange={e=>setNewTask({...newTask,description:e.target.value})} placeholder="Add some context..."/></label><div className="form-row"><label>Priority<select value={newTask.priority} onChange={e=>setNewTask({...newTask,priority:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label>Due date<input type="date" value={newTask.due_date} onChange={e=>setNewTask({...newTask,due_date:e.target.value})}/></label></div><div className="dialog-actions"><button type="button" onClick={()=>setTaskModal(false)}>Cancel</button><button className="primary-btn" type="submit">Create task</button></div></form></section></div>}
  </div>;
}
