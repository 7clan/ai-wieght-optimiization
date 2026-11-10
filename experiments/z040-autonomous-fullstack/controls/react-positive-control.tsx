// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Positive react-interaction
// control: faithful implementation of the radiostation Broadcast list
// contract (search, status filter, clear, empty state, labels, no fixed
// widths). Used to prove the evaluator accepts correct behavior.
import { useState } from 'react';

export default function ListView({ data }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const rows = (data || []).filter((row) => {
    const matchesQuery = !query || (row.title || '').toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === 'all' || row.status === status;
    return matchesQuery && matchesStatus;
  });
  return (
    <div>
      <label htmlFor="search">Search broadcasts</label>
      <input id="search" type="search" value={query}
             onChange={(e) => setQuery(e.target.value)} />
      <label htmlFor="status">Filter by status</label>
      <select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="all">All statuses</option>
        <option value="drafted">Drafted</option>
        <option value="cleared">Cleared</option>
        <option value="aired">Aired</option>
      </select>
      <button type="button" onClick={() => { setQuery(''); setStatus('all'); }}>
        Clear filters
      </button>
      <p aria-live="polite">Total: {rows.length}</p>
      {rows.length === 0 ? (
        <p data-testid="empty-state">No items match your filters.</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id}>
              <strong>{row.title}</strong> — {row.airtimeMin} min — {row.status}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
