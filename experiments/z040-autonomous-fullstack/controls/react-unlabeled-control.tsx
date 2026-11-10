// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: functionally correct
// filtering but no accessible labels. Proves the keyboard/accessibility
// oracle case alone discriminates (exact-case discrimination).
import { useState } from 'react';

export default function ListView({ data }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const rows = (data || []).filter((row) =>
    (!query || (row.title || '').toLowerCase().includes(query.toLowerCase()))
    && (status === 'all' || row.status === status));
  return (
    <div>
      <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="all">All</option>
        <option value="drafted">Drafted</option>
        <option value="cleared">Cleared</option>
        <option value="aired">Aired</option>
      </select>
      <button type="button" onClick={() => { setQuery(''); setStatus('all'); }}>Clear</button>
      <p>Total: {rows.length}</p>
      {rows.length === 0 ? <p data-testid="empty-state">No items match.</p> : (
        <ul>{rows.map((row) => <li key={row.id}><strong>{row.title}</strong> — {row.airtimeMin} min — {row.status}</li>)}</ul>
      )}
    </div>
  );
}
