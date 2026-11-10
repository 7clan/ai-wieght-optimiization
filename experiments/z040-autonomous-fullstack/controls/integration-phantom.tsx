// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: adds the item to the
// visible list locally even when the POST failed (fabricated success).
// Proves the no-phantom/visible-immediately oracle cases discriminate.
import { useEffect, useState } from 'react';

const ROUTE = '/api/radiostation-broadcasts';

export default function Manager() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [title, setTitle] = useState('');
  const [airtimeMin, setAirtimeMin] = useState('1');

  const load = async () => {
    const res = await fetch(ROUTE);
    const data = await res.json();
    setRows(data.broadcasts || []);
    setTotal(data.total ?? 0);
  };
  useEffect(() => { load(); }, []);
  const submit = async (e) => {
    e.preventDefault();
    let created = null;
    try {
      const res = await fetch(ROUTE, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ title, airtimeMin: Number(airtimeMin) }),
      });
      if (res.status === 201) created = await res.json();
    } catch { created = null; }
    const row = created || { id: `local-${Date.now()}`, title, airtimeMin: Number(airtimeMin), status: 'drafted' };
    setRows((prev) => [...prev, row]);       // phantom even on failure
    setTotal((t) => t + 1);                  // fabricated increment
    setTitle('');
  };
  return (
    <div>
      <form onSubmit={submit}>
        <label htmlFor="title">Title</label>
        <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label htmlFor="airtimeMin">Airtime minutes</label>
        <input id="airtimeMin" type="number" value={airtimeMin} onChange={(e) => setAirtimeMin(e.target.value)} />
        <button type="submit">Create</button>
      </form>
      <p>Total: {total}</p>
      <ul>{rows.map((row) => <li key={row.id}>{row.title} — {row.airtimeMin} min</li>)}</ul>
    </div>
  );
}
