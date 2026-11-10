// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: fetches the wrong
// endpoint, so every request 404s. Proves the create-201 oracle case
// discriminates (and that the shim does not silently fix paths).
import { useEffect, useState } from 'react';

export default function Manager() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [title, setTitle] = useState('');
  const [airtimeMin, setAirtimeMin] = useState('1');

  const load = async () => {
    const res = await fetch('/api/wrong-endpoint');
    if (!res.ok) return;
    const data = await res.json();
    setRows(data.broadcasts || []);
    setTotal(data.total ?? 0);
  };
  useEffect(() => { load(); }, []);
  const submit = async (e) => {
    e.preventDefault();
    await fetch('/api/wrong-endpoint', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title, airtimeMin: Number(airtimeMin) }),
    });
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
      <ul>{rows.map((row) => <li key={row.id}>{row.title}</li>)}</ul>
    </div>
  );
}
