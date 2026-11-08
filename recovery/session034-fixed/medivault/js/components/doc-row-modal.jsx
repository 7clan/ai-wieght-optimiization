/* ORIGIN: qwen-repaired.
   Base: M5 candidate r0c0 (Qwen2.5-Coder-0.5B). Bounded repairs:
   R1. broken className concat ("type-badge type-" + doc.docType outside
       braces - invalid JSX) -> template-literal expression.
   R2. undefined label/patient/date/starToggleLabel references -> computed
       locals from doc props.
   R3. first cell showed docType button instead of the document name ->
       name renders as the view trigger.
   R4. missing Rename action button -> added.
   R5. import/export stripped (no-build runtime), window global appended. */

const TYPE_LABELS = { lab: 'Lab', rx: 'Rx', insurance: 'Insurance', imaging: 'Imaging', consent: 'Consent' };

const DocRow = ({ doc, onView, onRename, onDelete, onStar }) => {
  const label = TYPE_LABELS[doc.docType] || doc.docType;
  return (
    <tr>
      <td>
        <button className="doc-name" onClick={() => onView(doc.id)}>{doc.name}</button>
      </td>
      <td>
        <span className={`type-badge type-${doc.docType}`}>{label}</span>
      </td>
      <td>{doc.patient}</td>
      <td>{doc.date}</td>
      <td>{doc.sizeKB + ' KB'}</td>
      <td>
        <button className="btn-icon" aria-label="Star" onClick={() => onStar(doc.id)}>
          {doc.starred ? '★' : '☆'}
        </button>
        <button className="btn-icon" aria-label="View" onClick={() => onView(doc.id)}>👁</button>
        <button className="btn-icon" aria-label="Rename" onClick={() => onRename(doc.id)}>✎</button>
        <button className="btn-icon danger" aria-label="Delete" onClick={() => onDelete(doc.id)}>🗑</button>
      </td>
    </tr>
  );
};

window.DocRow = DocRow;

const Modal = ({ title, onClose, children }) => {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="btn-icon" aria-label="Close" onClick={onClose}>x</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
};

window.Modal = Modal;
