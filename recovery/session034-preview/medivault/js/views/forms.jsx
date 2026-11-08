/* ORIGIN: qwen-repaired.
   Base: M7 candidate r0c1 (Qwen2.5-Coder-0.5B) - file-input reading logic
   (files[0].name / size/1024) preserved verbatim. Bounded repairs:
   R1. stray JSX after component close -> removed (syntax error).
   R2. RenameForm: useState(initialName) name collision -> renamed state var.
   R3. date state: 'today as string' (TS syntax in JS) -> computed ISO date.
   R4. submit buttons missing disabled binding -> wired to required fields.
   R5. labels/wire-up normalized to .label/.input/.select classes. */

const UploadForm = ({ folder, onSubmit, onCancel }) => {
  const [docType, setDocType] = useState('lab');
  const [patient, setPatient] = useState('');
  const [notes, setNotes] = useState('');
  const [fileName, setFileName] = useState('');
  const [sizeKB, setSizeKB] = useState(0);
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate] = useState(today);

  const handleFile = (event) => {
    if (event.target.files && event.target.files[0]) {
      setFileName(event.target.files[0].name);
      setSizeKB(Math.max(1, Math.round(event.target.files[0].size / 1024)));
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!fileName) return;
    onSubmit({ name: fileName, docType, patient, date, sizeKB, notes });
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label className="label" htmlFor="mv-file">Document (PDF, image, or text)</label>
        <input id="mv-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.txt,.doc,.docx" onChange={handleFile} />
        {fileName && <div className="file-name">Selected: {fileName} ({sizeKB} KB)</div>}
      </div>
      <div className="field">
        <label className="label" htmlFor="mv-type">Type</label>
        <select id="mv-type" className="select" value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="lab">Lab</option>
          <option value="rx">Rx</option>
          <option value="insurance">Insurance</option>
          <option value="imaging">Imaging</option>
          <option value="consent">Consent</option>
        </select>
      </div>
      <div className="field">
        <label className="label" htmlFor="mv-patient">Patient</label>
        <input id="mv-patient" className="input" type="text" value={patient} onChange={(e) => setPatient(e.target.value)} placeholder="e.g. A.K." />
      </div>
      <div className="field">
        <label className="label" htmlFor="mv-date">Date</label>
        <input id="mv-date" className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <div className="field">
        <label className="label" htmlFor="mv-notes">Notes</label>
        <input id="mv-notes" className="input" type="text" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" />
      </div>
      <div className="form-footer">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={!fileName}>Upload</button>
      </div>
    </form>
  );
};
window.UploadForm = UploadForm;

const NewFolderForm = ({ onSubmit, onCancel }) => {
  const [name, setName] = useState('');
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit(name.trim());
  };
  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label className="label" htmlFor="mv-folder">Folder name</label>
        <input id="mv-folder" className="input" type="text" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </div>
      <div className="form-footer">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={!name.trim()}>Create Folder</button>
      </div>
    </form>
  );
};
window.NewFolderForm = NewFolderForm;

const RenameForm = ({ initialName, onSubmit, onCancel }) => {
  const [name, setName] = useState(initialName || '');
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit(name.trim());
  };
  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label className="label" htmlFor="mv-rename">New name</label>
        <input id="mv-rename" className="input" type="text" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </div>
      <div className="form-footer">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={!name.trim()}>Save</button>
      </div>
    </form>
  );
};
window.RenameForm = RenameForm;
