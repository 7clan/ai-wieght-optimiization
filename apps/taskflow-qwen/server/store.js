const fs = require('node:fs');
function createStore(filePath) {
  let state = { projects: [], tasks: [] };
  // 2. write the load SETUP
  if (fs.existsSync(filePath)) {
    state = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  }
  // 3. write the first counter SETUP
  let pnext = 1;
  let tnext = 1;
  // 4. write the update SETUP
  function save() {
    const data = JSON.stringify(state);
    fs.writeFileSync(filePath, data);
  }
  function listProjects() {
    return state.projects.map(p => ({ ...p }))
  }
  function createProject(body) {
    if (typeof body.name !== 'string' || !body.name) {
      throw Error('invalid name');
    }
    const project = { id: 'p' + (pnext++), name: body.name,
                      createdAt: '2026-11-07' };
    state.projects.push(project);
    save();
    return { ...project };
  }
  function createTask(body) {
    if (!state.projects.some(p => p.id === String(body.projectId))) {
      throw Error('project not found: ' + body.projectId);
    }
    if (typeof body.title !== 'string' || !body.title) {
      throw Error('invalid title');
    }
    const priority = body.priority === undefined ? 'medium' : body.priority;
    const status = body.status === undefined ? 'todo' : body.status;
    if (!['low', 'medium', 'high'].includes(priority)) {
      throw Error('invalid priority');
    }
    if (!['todo', 'doing', 'done'].includes(status)) {
      throw Error('invalid status');
    }
    const task = { id: 't' + (tnext++), projectId: String(body.projectId),
                  title: body.title, priority: priority, status: status,
                  createdAt: '2026-11-07' };
    state.tasks.push(task);
    save();
    return { ...task };
  }
  function updateProject(id, body) {
    const project = state.projects.find(p => p.id === String(id));
    if (!project) throw Error('project not found: ' + id);
    if (body.name !== undefined) {
      if (typeof body.name !== 'string' || !body.name) {
        throw Error('invalid name');
      }
      project.name = body.name;
    }
    save();
    return { ...project };
  }
  function updateTask(id, body) {
    const task = state.tasks.find(t => t.id === String(id));
    if (!task) throw Error('task not found: ' + id);
    if (body.title !== undefined) {
      if (typeof body.title !== 'string' || !body.title) {
        throw Error('invalid title');
      }
      task.title = body.title;
    }
    if (body.priority !== undefined) {
      if (!['low', 'medium', 'high'].includes(body.priority)) {
        throw Error('invalid priority');
      }
      task.priority = body.priority;
    }
    if (body.status !== undefined) {
      if (!['todo', 'doing', 'done'].includes(body.status)) {
        throw Error('invalid status');
      }
      task.status = body.status;
    }
    save();
    return { ...task };
  }
  function deleteProject(id) {
    const project = state.projects.find(p => p.id === String(id));
    if (!project) throw Error('project not found: ' + id);
    state.projects = state.projects.filter(p => p.id !== String(id));
    state.tasks = state.tasks.filter(task => task.projectId !== String(id));
    save();
    return true;
  }
  function deleteTask(id) {
    const task = state.tasks.find(t => t.id === String(id));
    if (!task) throw Error('task not found: ' + id);
    const project = state.projects.find(p => p.id === String(task.projectId));
    if (!project) throw Error('project not found: ' + id);
    state.tasks = state.tasks.filter(t => t.id !== String(id));
    state.projects = state.projects.filter(p => p.id !== String(id));
    save();
    return true;
  }
  function listTasks(filter) {
    let tasks = state.tasks;
    if (typeof filter === 'undefined') return tasks;
    if (filter.projectId) tasks = tasks.filter(t => t.projectId === filter.projectId);
    if (filter.status) tasks = tasks.filter(t => t.status === filter.status);
    if (filter.q) tasks = tasks.filter(t => t.title.toLowerCase().includes(filter.q.toLowerCase()));
    return tasks;
  }
  return { listProjects, createProject, updateProject, deleteProject,
           listTasks, createTask, updateTask, deleteTask };
}
module.exports = createStore;
