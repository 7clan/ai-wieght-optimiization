// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Positive fullstack-integration
// control: a create form wired to the GET/POST route with fetch — loads the
// list on mount, creates on submit, shows errors, preserves form data,
// displays the total. Faithful to the radiostation Broadcast contract.
import { useEffect, useState } from 'react';

const ROUTE = '/api/radiostation-broadcasts';

export default function Manager() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [title, setTitle] = useState('');
  const [airtimeMin, setAirtimeMin] = useState('1');
  const [transmitterId, setTransmitterId] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    const res = await fetch(ROUTE);
    const data = await res.json();
    setRows(data.broadcasts || []);
    setTotal(data.total ?? 0);
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    const res = await fetch(ROUTE, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title, airtimeMin: Number(airtimeMin), transmitterId: transmitterId || undefined }),
    });
    if (res.status === 201) {
      setTitle('');
      await load();
    } else {
      const data = await res.json().catch(() => ({}));
      setError(data.message || `Request failed (${res.status})`);
    }
  };

  return (
    <div>
      <h1>Broadcast manager</h1>
      <form onSubmit={submit}>
        <label htmlFor="title">Title</label>
        <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label htmlFor="airtimeMin">Airtime minutes</label>
        <input id="airtimeMin" type="number" min="1" max="360" value={airtimeMin}
               onChange={(e) => setAirtimeMin(e.target.value)} />
        <label htmlFor="transmitterId">Transmitter</label>
        <select id="transmitterId" value={transmitterId} onChange={(e) => setTransmitterId(e.target.value)}>
          <option value="">None</option>
          <option value="parent-a">Transmitter A</option>
          <option value="parent-b">Transmitter B</option>
        </select>
        <button type="submit">Create</button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      <p>Total: {total}</p>
      <ul>
        {rows.map((row) => (
          <li key={row.id}><strong>{row.title}</strong> — {row.airtimeMin} min — {row.status}</li>
        ))}
      </ul>
    </div>
  );
}
