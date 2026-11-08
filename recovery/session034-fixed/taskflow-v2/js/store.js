/* ORIGIN: qwen-repaired.
   Base: S4.1a candidate r0c0 + S4.1b candidate r0c0 (Qwen2.5-Coder-0.5B).
   Teacher repairs (each fixes a defect caught by the real browser test suite):
   R1. getTasks() returned a PROJECT object (projects.find) instead of the
       project's task ARRAY -> "tasks.filter is not a function".
   R2. getData() re-parsed localStorage on every call, so mutations operated
       on throwaway copies -> added a cached _data state initialized once.
   R3. _listeners was never initialized and notify() was never defined,
       although every mutation called this.notify() -> added both.
   R4. subscribe()'s unsubscribe used `this` inside a plain function (undefined
       at call time) -> proper closure.
   R5. addProject/addTask used ++this.seq (NaN ids; seq lives in data) ->
       ids now derived from data.seq.
   R6. setTaskStatus/deleteTask/renameProject accessed this.tasks/this.projects
       (not on the store object) -> this._data.tasks/_data.projects.
   R7. seed: 2 projects / 6 tasks with string ids and ISO due dates, matching
       the app contract (Qwen seed had 3 tasks, numeric ids, Date objects). */

window.TaskFlowStore = {
  _listeners: [],

  seedData() {
    return {
      projects: [
        { id: 'p1', name: 'Website Redesign' },
        { id: 'p2', name: 'Mobile App' }
      ],
      tasks: [
        { id: 't1', projectId: 'p1', title: 'Design homepage mockup', status: 'todo', priority: 'high', due: '2026-11-20' },
        { id: 't2', projectId: 'p1', title: 'Implement navigation bar', status: 'doing', priority: 'medium', due: '2026-11-24' },
        { id: 't3', projectId: 'p1', title: 'Write CSS for pricing section', status: 'todo', priority: 'low', due: '2026-11-28' },
        { id: 't4', projectId: 'p2', title: 'Set up React Native project', status: 'done', priority: 'high', due: '2026-11-10' },
        { id: 't5', projectId: 'p2', title: 'Build login screen', status: 'doing', priority: 'medium', due: '2026-11-30' },
        { id: 't6', projectId: 'p2', title: 'Write API client', status: 'todo', priority: 'high', due: '2026-12-05' }
      ],
      seq: 7
    };
  },

  _data: null,

  load() {
    try {
      const raw = localStorage.getItem('taskflow-data');
      if (raw) {
        const data = JSON.parse(raw);
        if (data && Array.isArray(data.projects) && Array.isArray(data.tasks)) {
          return data;
        }
      }
    } catch (error) {
      console.error('Error loading taskflow data:', error);
    }
    return this.seedData();
  },

  getData() {
    if (!this._data) this._data = this.load();
    return this._data;
  },

  getTasks(projectId) {
    return this.getData().tasks.filter((t) => t.projectId === projectId);
  },

  save() {
    localStorage.setItem('taskflow-data', JSON.stringify(this._data || this.getData()));
  },

  notify() {
    this._listeners.forEach((fn) => fn());
  },

  addProject(name) {
    const data = this.getData();
    const id = 'p' + (++data.seq);
    data.projects.push({ id, name });
    this.save();
    this.notify();
    return id;
  },

  addTask(projectId, title, priority, due) {
    const data = this.getData();
    const task = { id: 't' + (++data.seq), projectId, title, status: 'todo', priority: priority || 'medium', due: due || '' };
    data.tasks.push(task);
    this.save();
    this.notify();
    return task.id;
  }
};

window.TaskFlowStore.setTaskStatus = function (taskId, status) {
  const task = this.getData().tasks.find((t) => t.id === taskId);
  if (!task) return;
  task.status = status;
  this.save();
  this.notify();
};

window.TaskFlowStore.deleteTask = function (taskId) {
  const data = this.getData();
  const i = data.tasks.findIndex((t) => t.id === taskId);
  if (i === -1) return;
  data.tasks.splice(i, 1);
  this.save();
  this.notify();
};

window.TaskFlowStore.renameProject = function (id, name) {
  const project = this.getData().projects.find((p) => p.id === id);
  if (!project) return;
  project.name = name;
  this.save();
  this.notify();
};

window.TaskFlowStore.subscribe = function (fn) {
  const listeners = this._listeners;
  listeners.push(fn);
  return function () {
    const i = listeners.indexOf(fn);
    if (i > -1) listeners.splice(i, 1);
  };
};
