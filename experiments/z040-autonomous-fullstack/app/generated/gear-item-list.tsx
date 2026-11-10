import { useState } from 'react';

export default function GearItemList({ data }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const rows = (data || []).filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (status === 'all' || row.status === status));
  return (
    <div>
      <label htmlFor="sensor-search">Search sensors</label>
      <input id="sensor-search" type="search" value={search}
             onChange={(event) => setSearch(event.target.value)} />
      <label htmlFor="sensor-status">Filter by status</label>
      <select id="sensor-status" value={status}
              onChange={(event) => setStatus(event.target.value)}>
        <option value="all">All statuses</option>
        <option value="calibrating">Calibrating</option>
        <option value="monitoring">Monitoring</option>
        <option value="retired">Retired</option>
      </select>
      <button type="button" onClick={() => { setSearch(''); setStatus('all'); }}>
        Clear filters
      </button>
      {rows.length === 0 ? (
        <p data-testid="empty-state">No sensors match your filters.</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id}>
              <strong>{row.label}</strong> — {row.reading} — {row.status}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}