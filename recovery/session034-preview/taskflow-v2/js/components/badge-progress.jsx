// Import statements, export statements, require(). This file runs as a plain browser script; React and ReactDOM are already global variables.
window.Badge = function Badge(props) {
  return (
    <span className={`badge badge-${props.status}`}>
      {props.status === 'todo' ? 'To Do' : props.status === 'doing' ? 'In Progress' : 'Done'}
    </span>
  );
};

window.ProgressBar = function ProgressBar(props) {
  const { value, max } = props;
  if (max === 0) {
    return (
      <div className="progress-track">
        <div className="progress-fill" style={{ width: '0%' }} />
        <small>0%</small>
      </div>
    );
  }
  const percent = Math.min(100, Math.round((value / max) * 100));
  return (
    <div className="progress-track">
      <div className="progress-fill" style={{ width: `${percent}%` }} />
      <small>{percent}%</small>
    </div>
  );
};
