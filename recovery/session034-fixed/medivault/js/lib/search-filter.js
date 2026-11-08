/* ORIGIN: qwen-repaired.
   Base: M4 candidate (Qwen2.5-Coder-0.5B). Bounded repairs:
   R1. name/patient/notes were ANDed (all three had to contain the query)
       -> OR semantics; empty query matches everything (documents with
       empty notes were being dropped entirely).
   R2. typeFilter argument was never used -> 'all' OR docType match. */

window.searchDocuments = function searchDocuments(docs, query, typeFilter) {
  const q = (query || '').toLowerCase();
  return docs.filter((doc) => {
    const matchesQuery =
      !q ||
      (doc.name && doc.name.toLowerCase().includes(q)) ||
      (doc.patient && doc.patient.toLowerCase().includes(q)) ||
      (doc.notes && doc.notes.toLowerCase().includes(q));
    const matchesType = !typeFilter || typeFilter === 'all' || doc.docType === typeFilter;
    return matchesQuery && matchesType;
  });
};
