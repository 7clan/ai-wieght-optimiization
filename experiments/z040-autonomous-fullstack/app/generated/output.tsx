import { useEffect, useState } from 'react';

export default function GearItemManager({ lockers }) {
  const [gear, setGear] = useState(null);
  const [total, setTotal] = useState(0);
  const [label, setLabel] = useState('');
  const [usageHours, setUsageHours] = useState(0);
  const [lockerId, setLockerId] = useState(null);

  const load = async () => {
    const response = await fetch('/api/gearhut-items');
    const data = await response.json();
    setGear(data.gear || []);
    setTotal(data.total ?? 0);
  };

  useEffect(() => { load(); }, []);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    const response = await fetch('/api/gearhut-items', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ label, usageHours, lockerId }),
    });
    if (response.status === 201) {
      setLabel('');
      await load();
    } else {
      const data = await response.json().catch(() => ({}));
      setError(data.error || `Request failed (${response.status})`);
    }
  };

  return (
    <div>
      <h1>Gear Item Manager</h1>
      <form onSubmit={submit}>
        <label htmlFor="label">Label</label>
        <input id="label" value={label} onChange={(event) => setLabel(event.target.value)} />
        <label htmlFor="usageHours">Usage Hours</label>
        <input id="usageHours" type="number" min="0" max="100" value={usageHours}
               onChange={(event) => setUsageHours(event.target.value)} />
        <label htmlFor="lockerId">Locker</label>
        <select id="lockerId" value={lockerId} onChange={(event) => setLockerId(event.target.value)}>
          {lockers.map((locker) => (
            <option key={locker.id} value={locker.id}>{locker.name}</option>
          ))}
        </select>
        <button type="submit">Create</button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      <p>Total: {total}</p>
      <ul>
        {gear.map((gearItem) => (
          <li key={gearItem.id}>
            <strong>{gearItem.label}</strong> — {gearItem.usageHours} — {gearItem.status}
          </li>
        ))}
      </ul>
    </div>
  );
}