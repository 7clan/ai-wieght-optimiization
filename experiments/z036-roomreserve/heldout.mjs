// RoomReserve HELD-OUT test — Session 036.
// NEVER shown to any generation track before scoring.  Boundary
// conditions, cross-file behavior, malformed payloads, persistence.
// Run: node heldout.mjs [--base http://127.0.0.1:3000]
import { spawnSync } from 'node:child_process';

const BASE = process.argv.includes('--base')
  ? process.argv[process.argv.indexOf('--base') + 1]
  : (process.env.BASE || 'http://127.0.0.1:3000');

const results = [];
let n = 0;
function check(name, cond, extra = '') {
  n += 1;
  results.push({ n, name, pass: !!cond, extra });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${String(n).padStart(2)} ${name}${extra ? ' — ' + extra : ''}`);
  return !!cond;
}
const j = (r) => { try { return JSON.parse(r); } catch { return null; } };
async function reseed() {
  const res = spawnSync('bun', ['run', 'db:reseed-roomreserve'], {
    cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
  });
  return res.status === 0;
}

async function main() {
  const H = { 'Content-Type': 'application/json' };
  await reseed();

  const rooms = (await (await fetch(`${BASE}/api/rooms`)).json()).rooms;
  const atlas = rooms.find(x => x.name === 'Atlas Boardroom');
  const breeze = rooms.find(x => x.name === 'Breeze Huddle');
  const cove = rooms.find(x => x.name === 'Cove Focus Room');

  // H1: fully-nested overlap is a conflict
  let r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: atlas.id, title: 'Nested', organizer: 'H', start: '2026-11-12T09:15', end: '2026-11-12T10:00' }),
  });
  check('H1 nested overlap (inside R1) -> 409', r.status === 409);

  // H2: zero-length window (start == end) -> 400, not 201/409
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: breeze.id, title: 'Zero', organizer: 'H', start: '2026-11-12T13:00', end: '2026-11-12T13:00' }),
  });
  check('H2 zero-length window -> 400 "End must be after start"',
    r.status === 400 && j(await r.text())?.error === 'End must be after start');

  // H3: date-only string (missing time) -> invalid format
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: breeze.id, title: 'DateOnly', organizer: 'H', start: '2026-11-12', end: '2026-11-13' }),
  });
  check('H3 date-only strings -> 400 "Invalid date format"',
    r.status === 400 && j(await r.text())?.error === 'Invalid date format');

  // H4: cross-midnight window is legal and listed under both days
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: breeze.id, title: 'Overnight', organizer: 'H', start: '2026-11-12T22:00', end: '2026-11-13T02:00' }),
  });
  check('H4 cross-midnight create -> 201', r.status === 201);
  r = await fetch(`${BASE}/api/reservations?date=2026-11-13`);
  let body = j(await r.text());
  const on13 = body?.reservations?.some(x => x.title === 'Overnight');
  r = await fetch(`${BASE}/api/reservations?date=2026-11-12`);
  body = j(await r.text());
  const on12 = body?.reservations?.some(x => x.title === 'Overnight');
  check('H5 cross-midnight appears on BOTH day filters', on12 && on13,
    `12=${on12} 13=${on13}`);

  // H6: same window as R1 in a DIFFERENT room is fine (rooms never
  // cross-conflict).  FIXTURE REPAIR #4 (Session 036, disclosed
  // 2026-11-08): the original used Breeze, but the seed corpus has
  // Standup 09:30-09:45 IN BREEZE overlapping the window, so the 409
  // was correct application behavior contradicting the fixture's intent
  // (same class as Session-035 fixture bug #11).  Cove has no morning
  // reservation.
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: cove.id, title: 'Parallel', organizer: 'H', start: '2026-11-12T09:00', end: '2026-11-12T10:30' }),
  });
  check('H6 identical window, different room -> 201', r.status === 201);

  // H7: PUT that only moves times still re-validates against others
  const list = (await (await fetch(`${BASE}/api/reservations`)).json()).reservations;
  const parallel = list.find(x => x.title === 'Parallel');
  r = await fetch(`${BASE}/api/reservations/${parallel.id}`, {
    method: 'PUT', headers: H,
    body: JSON.stringify({ roomId: atlas.id, start: '2026-11-12T09:30', end: '2026-11-12T11:00' }),
  });
  check('H7 PUT moving into R1 window in Atlas -> 409', r.status === 409);

  // H8: cancelled row resurrects its slot for POST
  const r1 = list.find(x => x.title === 'Quarterly Review');
  r = await fetch(`${BASE}/api/reservations/${r1.id}`, { method: 'DELETE' });
  check('H8 cancel R1 -> 200', r.status === 200);
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: JSON.stringify({ roomId: atlas.id, title: 'R1 slot reuse', organizer: 'H', start: '2026-11-12T09:00', end: '2026-11-12T10:30' }),
  });
  check('H9 freed slot is bookable again -> 201', r.status === 201);

  // H10: filter combination roomId+date
  r = await fetch(`${BASE}/api/reservations?roomId=${breeze.id}&date=2026-11-12`);
  body = j(await r.text());
  // FIXTURE REPAIR #4b (with #4): Parallel moved to Cove, so the Breeze
  // day filter yields Standup + Overnight = 2.
  check('H10 roomId+date combined filter -> Standup + Overnight only',
    r.status === 200 && body.reservations?.length === 2
    && body.reservations.every(x => x.roomName === 'Breeze Huddle'),
    `n=${body?.reservations?.length}`);

  // H11: malformed JSON body -> 400-family, never 500
  r = await fetch(`${BASE}/api/reservations`, {
    method: 'POST', headers: H,
    body: '{not json',
  });
  check('H11 malformed JSON -> 400 (not 500)',
    r.status >= 400 && r.status < 500, `status=${r.status}`);

  // H12: rooms minCapacity + q combined
  r = await fetch(`${BASE}/api/rooms?q=atlas&minCapacity=20`);
  body = j(await r.text());
  check('H12 rooms q+minCapacity combined -> empty (Atlas is 12)',
    r.status === 200 && body.rooms?.length === 0 && body.total === 0);

  const summary = results.filter(x => x.pass).length;
  console.log(`\nHELD-OUT: ${summary}/${n} checks passed`);
  process.exit(summary === n ? 0 : 1);
}

main().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
