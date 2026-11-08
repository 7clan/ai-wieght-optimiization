
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const formatDue = (due) => {
  if (!due) return 'No due date';
  const d = new Date(due);
  if (isNaN(d.getTime())) return 'No due date';
  return 'Due ' + MONTHS[d.getMonth()] + ' ' + d.getDate();
};
window.TaskCard = function TaskCard(props) {
  const { task, onToggle, onDelete } = props;
  return (
    <div className="card">
      <h3 onClick={() => onToggle(task.id)}>{task.title}</h3>
      <button className="btn-icon" onClick={() => onDelete(task.id)}>
        x
      </button>
      <div className="meta">
        {formatDue(task.due)}
      </div>
      <div className="status">
        <Badge status={task.status}>
          {task.status}
        </Badge>
        <span className={'chip chip-' + task.priority}>{task.priority}</span>
      </div>
    </div>
  );
};