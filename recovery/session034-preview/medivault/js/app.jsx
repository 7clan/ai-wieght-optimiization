/* ORIGIN: teacher-authored (integration layer, same honest classification
   as TaskFlow's app.jsx - the 0.5B model could not produce it within budget;
   failed M-candidates are preserved in experiments/zai-visual/generations/). */

window.useMediVaultState = function useMediVaultState() {
  const [data, setData] = useState(window.MediVaultStore.getData());
  const [activeFolderId, setActiveFolderId] = useState(null);
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [modal, setModal] = useState(null); // {kind:'upload'|'folder'|'rename-doc'|'rename-folder'|'view', id?}
  const [toast, setToast] = useState(null);

  useEffect(() => {
    const refresh = () => setData({ ...window.MediVaultStore.getData() });
    return window.MediVaultStore.subscribe(refresh);
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const activeFolder = data.folders.find((f) => f.id === activeFolderId) || data.folders[0];
  const documents = activeFolder ? window.MediVaultStore.getDocuments(activeFolder.id) : [];

  const openModal = (kind, id) => setModal({ kind, id });
  const closeModal = () => setModal(null);
  const selectFolder = (id) => {
    setActiveFolderId(id);
    setQuery('');
    setTypeFilter('all');
  };
  const submitUpload = (doc) => {
    window.MediVaultStore.addDocument({ ...doc, folderId: activeFolder.id });
    setModal(null);
    setToast({ kind: 'success', text: 'Document added to ' + activeFolder.name });
  };
  const submitFolder = (name) => {
    const id = window.MediVaultStore.addFolder(name);
    setActiveFolderId(id);
    setModal(null);
    setToast({ kind: 'success', text: 'Folder created' });
  };
  const submitRename = (name) => {
    if (modal.kind === 'rename-doc') window.MediVaultStore.renameDocument(modal.id, name);
    if (modal.kind === 'rename-folder') window.MediVaultStore.renameFolder(modal.id, name);
    setModal(null);
    setToast({ kind: 'success', text: 'Renamed' });
  };
  const deleteDoc = (id) => {
    window.MediVaultStore.deleteDocument(id);
    setToast({ kind: 'success', text: 'Document deleted' });
  };
  const deleteFolderWithDocs = (id) => {
    window.MediVaultStore.deleteFolder(id);
    if (activeFolderId === id) setActiveFolderId(null);
    setToast({ kind: 'success', text: 'Folder deleted' });
  };

  return {
    data, activeFolder, documents, query, typeFilter, modal, toast,
    setQuery, setTypeFilter, selectFolder, openModal, closeModal,
    submitUpload, submitFolder, submitRename, deleteDoc, deleteFolderWithDocs,
  };
};

window.App = function App() {
  const mv = window.useMediVaultState();
  const { activeFolder } = mv;

  if (!activeFolder) {
    return React.createElement('div', { className: 'app-shell' },
      React.createElement('h2', null, 'No folders yet'));
  }

  const viewingDoc = mv.modal && mv.modal.kind === 'view'
    ? mv.documents.find((d) => d.id === mv.modal.id) : null;
  const renamingDoc = mv.modal && mv.modal.kind === 'rename-doc'
    ? mv.documents.find((d) => d.id === mv.modal.id) : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="brand-mark" aria-hidden="true">✚</span>
        <h1 className="app-title">MediVault Lite</h1>
        <span className="brand-sub">Medical Records</span>
        <div className="spacer"></div>
        <button className="btn btn-ghost" onClick={() => mv.openModal('folder')}>+ New Folder</button>
        <button className="btn btn-primary" onClick={() => mv.openModal('upload')}>Upload Document</button>
      </header>
      <nav className="folder-tabs" aria-label="Folders">
        {mv.data.folders.map((f) => (
          <button
            key={f.id}
            className={'folder-tab' + (f.id === activeFolder.id ? ' active' : '')}
            onClick={() => mv.selectFolder(f.id)}
          >
            {f.name}
          </button>
        ))}
      </nav>
      <main className="vault-main">
        <VaultView
          folder={activeFolder}
          documents={mv.documents}
          onView={(id) => mv.openModal('view', id)}
          onRename={(id) => mv.openModal('rename-doc', id)}
          onDelete={mv.deleteDoc}
          onStar={(id) => window.MediVaultStore.toggleStar(id)}
          onUpload={() => mv.openModal('upload')}
          onNewFolder={() => mv.openModal('folder')}
          query={mv.query}
          onQuery={mv.setQuery}
          typeFilter={mv.typeFilter}
          onTypeFilter={mv.setTypeFilter}
        />
      </main>

      {mv.modal && mv.modal.kind === 'upload' && (
        <Modal title={'Upload to ' + activeFolder.name} onClose={mv.closeModal}>
          <UploadForm folder={activeFolder} onSubmit={mv.submitUpload} onCancel={mv.closeModal} />
        </Modal>
      )}
      {mv.modal && mv.modal.kind === 'folder' && (
        <Modal title="New Folder" onClose={mv.closeModal}>
          <NewFolderForm onSubmit={mv.submitFolder} onCancel={mv.closeModal} />
        </Modal>
      )}
      {renamingDoc && (
        <Modal title="Rename Document" onClose={mv.closeModal}>
          <RenameForm initialName={renamingDoc.name} onSubmit={mv.submitRename} onCancel={mv.closeModal} />
        </Modal>
      )}
      {viewingDoc && (
        <Modal title="Document Details" onClose={mv.closeModal}>
          <div className="doc-detail">
            <h3 className="doc-detail-name">{viewingDoc.name}</h3>
            <span className={`type-badge type-${viewingDoc.docType}`}>
              {{ lab: 'Lab', rx: 'Rx', insurance: 'Insurance', imaging: 'Imaging', consent: 'Consent' }[viewingDoc.docType] || viewingDoc.docType}
            </span>
            <div className="meta-grid">
              <div className="meta-item"><div className="k">Patient</div><div className="v">{viewingDoc.patient || '—'}</div></div>
              <div className="meta-item"><div className="k">Date</div><div className="v">{viewingDoc.date}</div></div>
              <div className="meta-item"><div className="k">Size</div><div className="v">{viewingDoc.sizeKB} KB</div></div>
              <div className="meta-item"><div className="k">Folder</div><div className="v">{activeFolder.name}</div></div>
              <div className="meta-item"><div className="k">Starred</div><div className="v">{viewingDoc.starred ? 'Yes' : 'No'}</div></div>
            </div>
            {viewingDoc.notes && <p className="doc-notes">{viewingDoc.notes}</p>}
            <p className="doc-hint">Metadata record only - no file content is stored.</p>
          </div>
        </Modal>
      )}
      {mv.toast && <div className={'toast toast-' + mv.toast.kind}>{mv.toast.text}</div>}
    </div>
  );
};
