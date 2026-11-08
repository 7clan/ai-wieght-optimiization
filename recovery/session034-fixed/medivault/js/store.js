/* ORIGIN: qwen-repaired.
   Base: M3 candidate (Qwen2.5-Coder-0.5B). Bounded repairs (data-model
   deviations from the contract caught by browser tests):
   R1. seed was a bare folders array with NO documents and no state object
       -> proper { folders, documents, seq } state with 8 seed documents.
   R2. documents were nested inside folder objects -> flat documents array
       with folderId (per contract; matches app/view wiring).
   R3. getDocuments threw on unknown folder and sorted by subtraction on
       ISO date strings -> returns [] and sorts by string comparison desc.
   R4. ids derived from folders.length + 1 (collision after deletion) ->
       data.seq counter.
   R5. load() without try/catch (JSON.parse throws on corrupt data) and
       no array validation -> guarded.
   R6. save()/notify() were missing although mutations called them;
       subscribe() added with closure unsubscribe (contract pattern). */

window.MediVaultStore = {
  _data: null,
  _listeners: [],

  seed() {
    return {
      folders: [
        { id: 'f1', name: 'Lab Results' },
        { id: 'f2', name: 'Prescriptions' },
        { id: 'f3', name: 'Insurance' }
      ],
      documents: [
        { id: 'd1', folderId: 'f1', name: 'Complete Blood Count.pdf', docType: 'lab', patient: 'A.K.', date: '2026-10-04', sizeKB: 320, notes: 'All values within normal range', starred: true },
        { id: 'd2', folderId: 'f1', name: 'Lipid Panel.pdf', docType: 'lab', patient: 'A.K.', date: '2026-09-18', sizeKB: 280, notes: '', starred: false },
        { id: 'd3', folderId: 'f1', name: 'HbA1c Result.pdf', docType: 'lab', patient: 'M.R.', date: '2026-10-28', sizeKB: 410, notes: 'Repeat in 3 months', starred: false },
        { id: 'd4', folderId: 'f2', name: 'Metformin 500mg Rx.jpg', docType: 'rx', patient: 'A.K.', date: '2026-10-05', sizeKB: 890, notes: 'Twice daily with meals', starred: false },
        { id: 'd5', folderId: 'f2', name: 'Amoxicillin Rx.pdf', docType: 'rx', patient: 'J.S.', date: '2026-08-22', sizeKB: 220, notes: '', starred: false },
        { id: 'd6', folderId: 'f3', name: 'Insurance Card 2026.jpg', docType: 'insurance', patient: 'A.K.', date: '2026-01-15', sizeKB: 1240, notes: 'Policy renewed', starred: true },
        { id: 'd7', folderId: 'f3', name: 'Claim #4471 Receipt.pdf', docType: 'insurance', patient: 'M.R.', date: '2026-07-30', sizeKB: 560, notes: 'Reimbursed', starred: false },
        { id: 'd8', folderId: 'f1', name: 'Chest X-ray Report.pdf', docType: 'imaging', patient: 'J.S.', date: '2026-10-12', sizeKB: 4800, notes: 'No acute findings', starred: false }
      ],
      seq: 9
    };
  },

  load() {
    try {
      const raw = localStorage.getItem('medivault-data');
      if (raw) {
        const data = JSON.parse(raw);
        if (data && Array.isArray(data.folders) && Array.isArray(data.documents)) {
          return data;
        }
      }
    } catch (e) {
      console.error('Error loading medivault data:', e);
    }
    return this.seed();
  },

  getData() {
    if (!this._data) this._data = this.load();
    return this._data;
  },

  getFolders() {
    return this.getData().folders;
  },

  getDocuments(folderId) {
    return this.getData().documents
      .filter((d) => d.folderId === folderId)
      .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  },

  save() {
    localStorage.setItem('medivault-data', JSON.stringify(this._data || this.getData()));
  },

  notify() {
    this._listeners.forEach((fn) => fn());
  },

  addFolder(name) {
    const data = this.getData();
    const id = 'f' + (++data.seq);
    data.folders.push({ id, name });
    this.save();
    this.notify();
    return id;
  },

  renameFolder(id, name) {
    const folder = this.getFolders().find((f) => f.id === id);
    if (!folder) return;
    folder.name = name;
    this.save();
    this.notify();
  },

  deleteFolder(id) {
    const data = this.getData();
    data.folders = data.folders.filter((f) => f.id !== id);
    data.documents = data.documents.filter((d) => d.folderId !== id);
    this.save();
    this.notify();
  },

  addDocument({ folderId, name, docType, patient, date, sizeKB, notes }) {
    const data = this.getData();
    const doc = {
      id: 'd' + (++data.seq), folderId, name, docType,
      patient: patient || '', date: date || new Date().toISOString().slice(0, 10),
      sizeKB: sizeKB || 1, notes: notes || '', starred: false
    };
    data.documents.push(doc);
    this.save();
    this.notify();
    return doc.id;
  },

  renameDocument(id, name) {
    const doc = this.getData().documents.find((d) => d.id === id);
    if (!doc) return;
    doc.name = name;
    this.save();
    this.notify();
  },

  deleteDocument(id) {
    const data = this.getData();
    const i = data.documents.findIndex((d) => d.id === id);
    if (i === -1) return;
    data.documents.splice(i, 1);
    this.save();
    this.notify();
  },

  toggleStar(id) {
    const doc = this.getData().documents.find((d) => d.id === id);
    if (!doc) return;
    doc.starred = !doc.starred;
    this.save();
    this.notify();
  },

  subscribe(fn) {
    const listeners = this._listeners;
    listeners.push(fn);
    return function () {
      const i = listeners.indexOf(fn);
      if (i > -1) listeners.splice(i, 1);
    };
  }
};
