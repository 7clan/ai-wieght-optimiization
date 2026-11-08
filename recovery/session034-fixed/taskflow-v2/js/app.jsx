/* ORIGIN: teacher-authored (integration layer).
   Qwen2.5-Coder-0.5B could not produce this file within budget:
   12 candidates across 2 tasks (S4.3a/S4.3b) failed acceptance
   (missing status-cycle map, toast timer, store-call wiring; syntax
   errors; logic inversions). The structure follows the best Qwen
   candidate (useTaskFlowState hook + App composition) but all
   behavior here is teacher-written. See ORIGIN.json and
   experiments/zai-visual/generations/staged-all-trackD/S4.3*.json
   for the failed Qwen attempts. */

window.useTaskFlowState = function useTaskFlowState() {
  const [data, setData] = useState(window.TaskFlowStore.getData());
  const [activeProjectId, setActiveProjectId] = useState(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const refresh = () => setData({ ...window.TaskFlowStore.getData() });
    const unsubscribe = window.TaskFlowStore.subscribe(refresh);
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const NEXT = { todo: 'doing', doing: 'done', done: 'todo' };
  const toggleTask = (id) => {
    const task = data.tasks.find((t) => t.id === id);
    if (task) window.TaskFlowStore.setTaskStatus(id, NEXT[task.status] || 'todo');
  };
  const deleteTask = (id) => {
    window.TaskFlowStore.deleteTask(id);
    setToast({ kind: 'success', text: 'Task deleted' });
  };
  const openModal = (kind) => setModal(kind);
  const closeModal = () => setModal(null);
  const submitTask = (title, priority, due) => {
    const project = activeProject(data, activeProjectId);
    if (!project) return;
    window.TaskFlowStore.addTask(project.id, title, priority, due);
    setModal(null);
    setToast({ kind: 'success', text: 'Task added' });
  };
  const submitProject = (name) => {
    const id = window.TaskFlowStore.addProject(name);
    setActiveProjectId(id);
    setModal(null);
    setQuery('');
    setFilter('all');
    setToast({ kind: 'success', text: 'Project created' });
  };
  const selectProject = (id) => {
    setActiveProjectId(id);
    setQuery('');
    setFilter('all');
    setSidebarOpen(false);
  };

  return {
    data, activeProjectId, query, filter, modal, toast, sidebarOpen,
    toggleTask, deleteTask, openModal, closeModal, submitTask, submitProject,
    selectProject, setQuery, setFilter, setSidebarOpen,
  };
};

function activeProject(data, activeProjectId) {
  return data.projects.find((p) => p.id === activeProjectId) || data.projects[0];
}

window.App = function App() {
  const tf = window.useTaskFlowState();
  const project = activeProject(tf.data, tf.activeProjectId);
  if (!project) {
    return React.createElement('div', { className: 'app-shell' },
      React.createElement('h2', null, 'No projects yet'));
  }
  const tasks = window.TaskFlowStore.getTasks(project.id);
  const counts = {};
  tf.data.projects.forEach((p) => {
    counts[p.id] = window.TaskFlowStore.getTasks(p.id).length;
  });

  return (
    <div className="app-shell">
      <header className="app-header">
        <button className="menu-btn" aria-label="Menu"
                onClick={() => tf.setSidebarOpen(!tf.sidebarOpen)}>&#9776;</button>
        <h1 className="app-title">TaskFlow</h1>
        <div className="spacer"></div>
        <button className="btn btn-ghost" onClick={() => tf.openModal('project')}>
          + New Project
        </button>
      </header>
      <div className="app-body">
        <Sidebar
          projects={tf.data.projects}
          activeId={project.id}
          sidebarOpen={tf.sidebarOpen}
          onSelect={tf.selectProject}
          onNewProject={() => tf.openModal('project')}
          counts={counts}
        />
        {tf.sidebarOpen && <div className="scrim" onClick={() => tf.setSidebarOpen(false)}></div>}
        <main className="main-content">
          <TaskListView
            project={project}
            tasks={tasks}
            onToggle={tf.toggleTask}
            onDelete={tf.deleteTask}
            onNewTask={() => tf.openModal('task')}
            query={tf.query}
            onQuery={tf.setQuery}
            filter={tf.filter}
            onFilter={tf.setFilter}
          />
        </main>
      </div>
      {tf.modal === 'task' && (
        <Modal title="New Task" onClose={tf.closeModal}>
          <NewTaskForm project={project} onSubmit={tf.submitTask} onCancel={tf.closeModal} />
        </Modal>
      )}
      {tf.modal === 'project' && (
        <Modal title="New Project" onClose={tf.closeModal}>
          <NewProjectForm onSubmit={tf.submitProject} onCancel={tf.closeModal} />
        </Modal>
      )}
      {tf.toast && (
        <div className={'toast toast-' + tf.toast.kind}>{tf.toast.text}</div>
      )}
    </div>
  );
};
