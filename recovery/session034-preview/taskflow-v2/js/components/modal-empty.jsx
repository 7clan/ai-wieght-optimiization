window.EmptyState = function EmptyState(props) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{props.icon}</div>
      <h2 className="modal-title">{props.title}</h2>
      <p>{props.hint}</p>
      {props.action}
    </div>
  );
};

window.Modal = function Modal(props) {
  return (
    <div className="modal-overlay" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{props.title}</h2>
          <button onClick={props.onClose}>X</button>
        </div>
        <div className="modal-body">{props.children}</div>
      </div>
    </div>
  );
};