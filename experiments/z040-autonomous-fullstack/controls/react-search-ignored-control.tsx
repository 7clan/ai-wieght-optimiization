// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: renders the list with
// a search box and status filter, but the search box is decorative (state
// never applied). Proves the search oracle cases discriminate.
import { useState } from 'react';

export default function ListView({ data }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const rows = (data || []).filter((row) => status === 'all' || row.status === status);
  return (
    <div>
      <label htmlFor="search">Search broadcasts</label>
      <input id="search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
      <label htmlFor="status">Filter by status</label>
      <select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="all">All statuses</option>
        <option value="drafted">Drafted</option>
        <option value="cleared">Cleared</option>
        <option value="aired">Aired</option>
      </select>
      <p>Total: {rows.length}</p>
      {rows.length === 0 ? <p data-testid="empty-state">No items match.</p> : (
        <ul>{rows.map((row) => <li key={row.id}><strong>{row.title}</strong> — {row.airtimeMin} min — {row.status}</li>)}</ul>
      )}
    </div>
  );
}
