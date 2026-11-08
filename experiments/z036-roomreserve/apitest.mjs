// RoomReserve frozen API acceptance test — Session 036.
// FROZEN BEFORE GENERATION (with SPEC.md). 18 ordered public checks + 2
// post-restart persistence checks.
// Run: node apitest.mjs [--base http://127.0.0.1:3000] [--phase pre|post-restart]
import { spawnSync } from 'node:child_process';

const BASE = process.argv.includes('--base')
  ? process.argv[process.argv.indexOf('--base') + 1]
  : (process.env.BASE || 'http://127.0.0.1:3000');
const PHASE = process.argv.includes('--phase')
  ? process.argv[process.argv.indexOf('--phase') + 1] : 'pre';

const results = [];
let n = 0;
function check(name, cond, extra = '') {
  n += 1;
  results.push({ n, name, pass: !!cond, extra });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${String(n).padStart(2)} ${name}${extra ? ' — ' + extra : ''}`);
  return !!cond;
}
const j = (r) => { try { return JSON.parse(r); } catch { return null; } };

async function wipe() {
  const res = spawnSync('bun', ['run', 'db:reseed-roomreserve'], {
    cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
  });
  return res.status === 0;
}

const TEST_DATE = '2026-11-12';

async function main() {
  const H = { 'Content-Type': 'application/json' };

  if (PHASE === 'pre') {
    // ---------- rooms ----------
    await wipe();
    let r = await fetch(`${BASE}/api/rooms`);
    let body = j(await r.text());
    check('GET /api/rooms 200, 4 seeded rooms, name-ascending',
      r.status === 200 && body && Array.isArray(body.rooms)
      && body.rooms.length === 4 && body.total === 4
      && body.rooms[0].name === 'Atlas Boardroom'
      && body.rooms[3].name === 'Dune Workshop',
      `n=${body?.rooms?.length}`);

    r = await fetch(`${BASE}/api/rooms?q=cove`);
    body = j(await r.text());
    check('GET /api/rooms?q=cove case-insensitive -> 1 (Cove Focus Room)',
      r.status === 200 && body.rooms?.length === 1
      && body.rooms[0].name === 'Cove Focus Room');

    r = await fetch(`${BASE}/api/rooms?minCapacity=8`);
    body = j(await r.text());
    check('GET /api/rooms?minCapacity=8 -> Atlas + Dune only',
      r.status === 200 && body.rooms?.length === 2
      && body.rooms.every(x => x.capacity >= 8));

    const rooms = (await (await fetch(`${BASE}/api/rooms`)).json()).rooms;
    const atlas = rooms.find(x => x.name === 'Atlas Boardroom');
    const breeze = rooms.find(x => x.name === 'Breeze Huddle');

    r = await fetch(`${BASE}/api/rooms/${atlas.id}`);
    body = j(await r.text());
    check('GET /api/rooms/:id 200 with room + reservations (newest first)',
      r.status === 200 && body.room?.name === 'Atlas Boardroom'
      && Array.isArray(body.room?.reservations)
      && body.room.reservations.every(x => x.roomId === atlas.id)
      && body.room.reservations.length >= 2
      && body.room.reservations[0].start >= body.room.reservations[1].start);

    r = await fetch(`${BASE}/api/rooms/does-not-exist`);
    check('GET /api/rooms/:id unknown -> 404 {error:"Room not found"}',
      r.status === 404 && j(await r.text())?.error === 'Room not found');

    // ---------- reservation listing & search ----------
    r = await fetch(`${BASE}/api/reservations`);
    body = j(await r.text());
    check('GET /api/reservations default: confirmed only, start-ascending, roomName joined',
      r.status === 200 && body.reservations?.length === 5
      && body.total === 5
      && body.reservations.every(x => x.status === 'confirmed'
        && typeof x.roomName === 'string')
      && body.reservations[0].start <= body.reservations[4].start,
      `n=${body?.reservations?.length}`);

    r = await fetch(`${BASE}/api/reservations?date=${TEST_DATE}`);
    body = j(await r.text());
    check(`GET /api/reservations?date=${TEST_DATE} -> 4 (R1,R2,R3,R4; not R5, not cancelled R6)`,
      r.status === 200 && body.reservations?.length === 4
      && body.reservations.every(x => x.start.startsWith(TEST_DATE)));

    r = await fetch(`${BASE}/api/reservations?roomId=${breeze.id}`);
    body = j(await r.text());
    check('GET /api/reservations?roomId -> only that room (Standup)',
      r.status === 200 && body.reservations?.length === 1
      && body.reservations[0].title === 'Standup');

    r = await fetch(`${BASE}/api/reservations?includeCancelled=1`);
    body = j(await r.text());
    check('GET ?includeCancelled=1 -> 6 incl. Cancelled Planning',
      r.status === 200 && body.reservations?.length === 6
      && body.reservations.some(x => x.title === 'Cancelled Planning'
        && x.status === 'cancelled'));

    r = await fetch(`${BASE}/api/reservations?q=ava`);
    body = j(await r.text());
    check('GET ?q=ava (organizer) case-insensitive -> R1 only',
      r.status === 200 && body.reservations?.length === 1
      && body.reservations[0].organizer === 'Ava Chen');

    // ---------- POST validation order & conflicts ----------
    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: '  ', organizer: 'X', start: '2026-11-12T13:00', end: '2026-11-12T14:00' }),
    });
    body = j(await r.text());
    check('POST blank title -> 400 "Title is required" (validation order 1)',
      r.status === 400 && body?.error === 'Title is required');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'T', organizer: '', start: '2026-11-12T13:00', end: '2026-11-12T14:00' }),
    });
    check('POST empty organizer -> 400 "Organizer is required"',
      r.status === 400 && j(await r.text())?.error === 'Organizer is required');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: 'nope', title: 'T', organizer: 'O', start: '2026-11-12T13:00', end: '2026-11-12T14:00' }),
    });
    check('POST unknown room -> 404 "Room not found"',
      r.status === 404 && j(await r.text())?.error === 'Room not found');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'T', organizer: 'O', start: 'tomorrow 9', end: '2026-11-12T14:00' }),
    });
    check('POST malformed date -> 400 "Invalid date format"',
      r.status === 400 && j(await r.text())?.error === 'Invalid date format');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'T', organizer: 'O', start: '2026-11-12T15:00', end: '2026-11-12T14:00' }),
    });
    check('POST end before start -> 400 "End must be after start"',
      r.status === 400 && j(await r.text())?.error === 'End must be after start');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'Overlapping', organizer: 'O', start: '2026-11-12T10:00', end: '2026-11-12T10:15' }),
    });
    body = j(await r.text());
    check('POST overlap with R1 (09:00-10:30) -> 409 "Time conflict with an existing reservation"',
      r.status === 409 && body?.error === 'Time conflict with an existing reservation');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'Back-to-back', organizer: 'O', start: '2026-11-12T10:30', end: '2026-11-12T11:00' }),
    });
    body = j(await r.text());
    check('POST back-to-back (start==R1.end) -> 201 (boundary: touching is NOT overlap)',
      r.status === 201 && body?.reservation?.status === 'confirmed');

    r = await fetch(`${BASE}/api/reservations`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ roomId: atlas.id, title: 'Cancelled-slot reuse', organizer: 'O', start: '2026-11-12T14:00', end: '2026-11-12T15:00' }),
    });
    body = j(await r.text());
    check('POST over CANCELLED R6 window -> 201 (cancelled never blocks)',
      r.status === 201 && body?.reservation?.title === 'Cancelled-slot reuse');

    // ---------- PUT edit ----------
    r = await fetch(`${BASE}/api/reservations`);
    const list = (await r.json()).reservations;
    const backToBack = list.find(x => x.title === 'Back-to-back');
    r = await fetch(`${BASE}/api/reservations/${backToBack.id}`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({ start: '2026-11-12T09:15', end: '2026-11-12T09:20' }),
    });
    check('PUT edit into R1 window -> 409 (self-excluded overlap check)',
      r.status === 409 && j(await r.text())?.error === 'Time conflict with an existing reservation');

    r = await fetch(`${BASE}/api/reservations/${backToBack.id}`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({ title: 'Back-to-back (moved)' }),
    });
    body = j(await r.text());
    check('PUT title-only edit of own window -> 200 (no self-conflict)',
      r.status === 200 && body?.reservation?.title === 'Back-to-back (moved)');

    // ---------- DELETE = cancellation ----------
    r = await fetch(`${BASE}/api/reservations/${backToBack.id}`, { method: 'DELETE' });
    body = j(await r.text());
    check('DELETE -> 200, status becomes "cancelled" (soft cancel)',
      r.status === 200 && body?.reservation?.status === 'cancelled');

    r = await fetch(`${BASE}/api/reservations/${backToBack.id}`, { method: 'DELETE' });
    check('DELETE again -> 200 (idempotent cancel)',
      r.status === 200 && j(await r.text())?.reservation?.status === 'cancelled');

    r = await fetch(`${BASE}/api/reservations`);
    body = j(await r.text());
    check('after cancels, default list back to 5 confirmed; slot reusable',
      r.status === 200 && body.total === 5);

    r = await fetch(`${BASE}/api/reservations/nope`, { method: 'DELETE' });
    check('DELETE unknown -> 404 "Reservation not found"',
      r.status === 404 && j(await r.text())?.error === 'Reservation not found');

    const summary = results.filter(x => x.pass).length;
    console.log(`\nAPI: ${summary}/${n} checks passed (pre phase)`);
    process.exit(summary === n ? 0 : 1);
  }

  if (PHASE === 'post-restart') {
    let r = await fetch(`${BASE}/api/reservations?includeCancelled=1`);
    const body = j(await r.text());
    const total = body?.total;
    check('after server restart: list still 200', r.status === 200 && !!body);
    check(`after server restart: same row count (SQLite persisted) — total=${total} expected=6`,
      total === 6, `total=${total}`);
    console.log(`\nAPI: ${results.filter(x => x.pass).length}/${n} checks passed (post-restart phase)`);
    process.exit(results.every(x => x.pass) ? 0 : 1);
  }
}

main().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
