
const NewTaskForm = ({ project, onSubmit, onCancel }) => {
  const [title, setTitle] = useState('');
  const [priority, setPriority] = useState('medium');
  const [due, setDue] = useState('');

  const validateTitle = () => {
    if (!title.trim()) {
      return <div className='field-error'>Title is required</div>;
    }
    return null;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (validateTitle()) {
      return;
    }
    onSubmit(title, priority, due);
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2 className='modal-sub'>{`New task in ${project.name}`}</h2>
      <div className="field">
        <label htmlFor="title">Title:</label>
        <input
          type="text"
          id="title"
          className="input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        {validateTitle()}
      </div>
      <div className="field">
        <label htmlFor="priority">Priority:</label>
        <select
          id="priority"
          className="select"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="due">Due Date:</label>
        <input
          type="date"
          id="due"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </div>
      <button type="submit">Add Task</button>
      <button onClick={onCancel}>Ghost Cancel</button>
    </form>
  );
};

window.NewTaskForm = NewTaskForm;



const NewProjectForm = ({ onSubmit, onCancel }) => {
  const [name, setName] = useState('');

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!name.trim()) {
      return (
        <div className="field-error">
          Project name is required
        </div>
      );
    }
    onSubmit(name);
  };

  return (
    <form onSubmit={handleSubmit}>
      <label htmlFor="Project name">Project name</label>
      <input
        type="text"
        id="Project name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <button type="submit" disabled={!name.trim()}>
        Cancel
      </button>
      <button type="submit">Create Project</button>
    </form>
  );
};

window.NewProjectForm = NewProjectForm;
