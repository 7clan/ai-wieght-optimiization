// TRUSTED TEACHER CONTROL — NOT QWEN CODE. Negative: infinite render loop
// via setState in effect. Proves the watchdog bounds runaway candidates
// fail-closed.
import { useEffect, useState } from 'react';

export default function ListView({ data }) {
  const [, setTick] = useState(0);
  useEffect(() => { setTick((t) => t + 1); });
  return <ul>{(data || []).map((row) => <li key={row.id}>{row.title}</li>)}</ul>;
}
