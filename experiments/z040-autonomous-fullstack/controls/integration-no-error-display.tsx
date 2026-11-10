// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: creation works but
// failed submissions are silently swallowed (no error display). Proves the
// 400/404/409 error-visibility oracle cases discriminate.
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
    const res = await fetch(ROUTE, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title, airtimeMin: Number(airtimeMin) }),
    });
    if (res.status === 201) { setTitle(''); await load(); }
    // errors deliberately ignored
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
