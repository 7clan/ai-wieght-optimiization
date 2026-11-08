/* ORIGIN: qwen-repaired.
   Base: S3.2b candidate r0c0 (Qwen2.5-Coder-0.5B, syntax-valid after
   mechanical transform). Teacher repairs (each verified in browser):
   R1. <Input>/<Select> -> lowercase <input>/<select> (Input/Select
       components do not exist - runtime crash).
   R2. removed local useState for `visible`; recompute per render from
       props (search/filter changes were ignored).
   R3. handleToggle/handleDelete: prevVisible.filter(taskId) is a
       TypeError (filter needs a function); now delegate directly to
       props.onToggle/onDelete.
   R4. defined doneCount (was undefined -> ReferenceError).
   R5. props.tasks -> tasks (destructured param; `props` undefined).
   R6. added the primary "New Task" button next to the heading. */

const TaskListView = ({ project, tasks, onToggle, onDelete, onNewTask, query, onQuery, filter, onFilter }) => {
  const visible = window.filterTasks(tasks, query, filter);
  const doneCount = visible.filter((t) => t.status === 'done').length;

  const handleQueryChange = (event) => {
    onQuery(event.target.value);
  };

  const handleFilterChange = (event) => {
    onFilter(event.target.value);
  };

  return (
    <div>
      <div className="view-head">
        <h2>{project.name}</h2>
        <button className="btn btn-primary" onClick={onNewTask}>New Task</button>
      </div>
      <div className="toolbar">
        <input className="input" type="text" placeholder="Search tasks..." value={query} onChange={handleQueryChange} />
        <select className="select" value={filter} onChange={handleFilterChange}>
          <option value="all">All</option>
          <option value="todo">To Do</option>
          <option value="doing">In Progress</option>
          <option value="done">Done</option>
        </select>
      </div>
      <ProgressBar value={doneCount} max={visible.length} />
      {visible.length > 0 ? (
        <div className="task-grid">
          {visible.map((task) => (
            <TaskCard key={task.id} task={task} onToggle={onToggle} onDelete={onDelete} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon="📋"
          title={tasks.length ? 'No matching tasks' : 'No tasks yet'}
          hint={tasks.length ? 'Try a different search or filter.' : 'Create your first task to get started.'}
        />
      )}
    </div>
  );
};

window.TaskListView = TaskListView;
