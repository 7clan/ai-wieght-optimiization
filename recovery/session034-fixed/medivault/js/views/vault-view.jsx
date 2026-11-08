/* ORIGIN: qwen-repaired.
   Base: M6 candidate r0c0 (Qwen2.5-Coder-0.5B). Bounded repairs:
   R1. fictional imports from '@medivault-lite/vault-view' stripped.
   R2. fictional <Toolbar>/<Input>/<Select>/<Table> components -> real
       lowercase elements with app classes.
   R3. select options had labels but no values -> value attributes added.
   R4. empty state rendered unconditionally below the table ->
       conditional (visible.length ? table : empty-state).
   R5. documentCount(undefined) -> visible.length inline.
   R6. multiple root elements -> wrapped in one container div.
   R7. table missing <table>/<thead>/<tbody> markup -> added. */

const VaultView = ({ folder, documents, onView, onRename, onDelete, onStar, onUpload, onNewFolder, query, onQuery, typeFilter, onTypeFilter }) => {
  const visible = window.searchDocuments(documents, query, typeFilter);

  return (
    <div className="vault-view">
      <div className="view-head">
        <h2>{folder.name}</h2>
        <span className="count">{visible.length} of {documents.length} documents</span>
        <div className="spacer"></div>
        <button className="btn btn-ghost" onClick={onNewFolder}>+ New Folder</button>
        <button className="btn btn-primary" onClick={onUpload}>Upload Document</button>
      </div>
      <div className="toolbar">
        <input
          className="input"
          type="text"
          placeholder="Search name, patient, notes..."
          value={query}
          onChange={(e) => onQuery(e.target.value)}
        />
        <select className="select" value={typeFilter} onChange={(e) => onTypeFilter(e.target.value)}>
          <option value="all">All Types</option>
          <option value="lab">Lab</option>
          <option value="rx">Rx</option>
          <option value="insurance">Insurance</option>
          <option value="imaging">Imaging</option>
          <option value="consent">Consent</option>
        </select>
      </div>
      {visible.length > 0 ? (
        <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Type</th><th>Patient</th><th>Date</th><th>Size</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((doc) => (
              <DocRow key={doc.id} doc={doc} onView={onView} onRename={onRename} onDelete={onDelete} onStar={onStar} />
            ))}
          </tbody>
        </table>
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-icon">🗂️</div>
          <h3>{documents.length ? 'No matching documents' : 'This folder is empty'}</h3>
          <p>{documents.length ? 'Try a different search or type filter.' : 'Upload your first document to get started.'}</p>
        </div>
      )}
    </div>
  );
};

window.VaultView = VaultView;
