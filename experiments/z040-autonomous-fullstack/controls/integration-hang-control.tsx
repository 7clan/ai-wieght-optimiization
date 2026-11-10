// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: mount-time infinite
// fetch loop. Proves the watchdog bounds runaway candidates fail-closed.
import { useEffect, useState } from 'react';

export default function Manager() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let alive = true;
    const loop = async () => {
      while (alive) {
        const res = await fetch('/api/broadcasts');
        setRows((await res.json()).broadcasts || []);
      }
    };
    loop();
    return () => { alive = false; };
  }, []);
  return <ul>{rows.map((r) => <li key={r.id}>{r.title}</li>)}</ul>;
}
