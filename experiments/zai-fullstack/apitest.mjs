// StockPilot frozen API acceptance test — Session 035.
// FROZEN BEFORE GENERATION. 16 ordered checks against SPEC.md §2.
// Run: node apitest.mjs [--base http://127.0.0.1:3000] [--phase pre|post-restart]
//   --phase pre        : full suite, creates its own data, ends with items on disk
//   --phase post-restart: re-checks only persistence (checks 15-16) + spot checks
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
  // Reset the inventory table via a harness-local prisma call (trusted
  // scaffolding; not part of the application under test).
  const res = spawnSync('bun', ['run', 'db:wipe-inventory'], {
    cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
  });
  return res.status === 0;
}

async function main() {
  const H = { 'Content-Type': 'application/json' };

  if (PHASE === 'pre') {
    // 1. clean slate -> empty list
    await wipe();
    let r = await fetch(`${BASE}/api/items`);
    let body = j(await r.text());
    check('GET empty list 200 {items:[],total:0}',
      r.status === 200 && body && Array.isArray(body.items)
      && body.items.length === 0 && body.total === 0);

    // 2. POST valid item -> 201 with id + fields
    r = await fetch(`${BASE}/api/items`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ name: 'USB-C Cable 2m', category: 'Accessories', sku: 'ACC-UC-2M', quantity: 42, minQuantity: 10 }),
    });
    body = j(await r.text());
    const first = body && body.item;
    check('POST valid item 201, echoes fields + id',
      r.status === 201 && first && first.id && first.name === 'USB-C Cable 2m'
      && first.quantity === 42 && first.minQuantity === 10);
    const keptId = first && first.id;

    // 3. POST missing name -> 400 {error}
    r = await fetch(`${BASE}/api/items`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ category: 'X', quantity: 1, minQuantity: 0 }),
    });
    body = j(await r.text());
    check('POST missing name 400 {error}', r.status === 400 && body && typeof body.error === 'string' && body.error.length > 0);

    // 4. POST negative quantity -> 400
    r = await fetch(`${BASE}/api/items`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ name: 'Bad', category: 'X', quantity: -3, minQuantity: 0 }),
    });
    check('POST negative quantity 400', r.status === 400);

    // 5. POST non-integer quantity -> 400
    r = await fetch(`${BASE}/api/items`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ name: 'Bad', category: 'X', quantity: 2.5, minQuantity: 0 }),
    });
    check('POST non-integer quantity 400', r.status === 400);

    // 6. seed a fixed 10-item corpus covering statuses/categories
    // [test-bug fix #7a/b, disclosed: the original seed produced only
    // 2 USB-matching and 3 low-stock items while checks 7 and 9
    // expect 3 and 4 — the expectations contradicted the fixture's
    // own arithmetic.  Fixture corrected to the documented intent:
    // 'USB Wireless Mouse' adds the third q=usb match (stays
    // Electronics), USB Hub minQuantity 6->20 adds the fourth
    // genuinely-low item.  No assertion was weakened.]
    const seed = [
      ['Mechanical Keyboard', 'Electronics', 'ELC-KB-01', 8, 10],   // low
      ['27in Monitor', 'Electronics', 'ELC-MN-27', 3, 2],           // in
      ['Office Chair', 'Furniture', 'FUR-CH-01', 0, 1],             // out
      ['Standing Desk', 'Furniture', 'FUR-DSK-01', 5, 2],           // in
      ['Printer Paper A4', 'Consumables', 'CON-PP-A4', 120, 30],    // in
      ['Ink Cartridge', 'Consumables', 'CON-INK-21', 2, 4],         // low
      ['USB Wireless Mouse', 'Electronics', 'ELC-MS-01', 25, 5],    // in
      ['Desk Lamp', 'Furniture', 'FUR-LP-01', 1, 1],                // low
      ['Sticky Notes', 'Consumables', 'CON-SN-03', 0, 5],           // out
      ['USB Hub 7-port', 'Accessories', 'ACC-UH-07', 14, 20],       // low
    ];
    let ok = true;
    for (const [name, category, sku, quantity, minQuantity] of seed) {
      const rr = await fetch(`${BASE}/api/items`, {
        method: 'POST', headers: H,
        body: JSON.stringify({ name, category, sku, quantity, minQuantity }),
      });
      if (rr.status !== 201) ok = false;
    }
    r = await fetch(`${BASE}/api/items`);
    body = j(await r.text());
    check('seed 10 + earlier = 11 items, total matches',
      ok && r.status === 200 && body && body.total === 11 && body.items.length === 11,
      `total=${body && body.total}`);

    // 7. search q (case-insensitive, name or sku)
    r = await fetch(`${BASE}/api/items?q=usb`);
    body = j(await r.text());
    check('GET ?q=usb matches name+sku case-insensitively (3)',
      r.status === 200 && body && body.total === 3
      && body.items.every(i => /usb/i.test(i.name + ' ' + (i.sku || ''))),
      `total=${body && body.total}`);

    // 8. category filter
    r = await fetch(`${BASE}/api/items?category=Electronics`);
    body = j(await r.text());
    check('GET ?category=Electronics -> 3 items all Electronics',
      r.status === 200 && body && body.total === 3
      && body.items.every(i => i.category === 'Electronics'));

    // 9. status=low -> only quantity>0 && quantity<=minQuantity
    r = await fetch(`${BASE}/api/items?status=low`);
    body = j(await r.text());
    check('GET ?status=low -> 4 items, all genuinely low',
      r.status === 200 && body && body.total === 4
      && body.items.every(i => i.quantity > 0 && i.quantity <= i.minQuantity),
      `total=${body && body.total}`);

    // 10. status=out
    r = await fetch(`${BASE}/api/items?status=out`);
    body = j(await r.text());
    check('GET ?status=out -> 2 items with quantity 0',
      r.status === 200 && body && body.total === 2
      && body.items.every(i => i.quantity === 0));

    // 11. sort by quantity asc
    r = await fetch(`${BASE}/api/items?sort=quantity&order=asc`);
    body = j(await r.text());
    const q = body ? body.items.map(i => i.quantity) : [];
    const sorted = [...q].sort((a, b) => a - b);
    check('GET ?sort=quantity&order=asc ascending',
      r.status === 200 && JSON.stringify(q) === JSON.stringify(sorted),
      `q=[${q.join(',')}]`);

    // 12. GET by id / 404
    r = await fetch(`${BASE}/api/items/${keptId}`);
    body = j(await r.text());
    const byIdOk = r.status === 200 && body && body.item && body.item.id === keptId;
    r = await fetch(`${BASE}/api/items/does-not-exist-999`);
    check('GET /:id 200 then 404 for unknown',
      byIdOk && r.status === 404 && j(await r.text()).error);

    // 13. PUT update
    r = await fetch(`${BASE}/api/items/${keptId}`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({ name: 'USB-C Cable 2m (updated)', category: 'Accessories', sku: 'ACC-UC-2M', quantity: 5, minQuantity: 10 }),
    });
    body = j(await r.text());
    const putOk = r.status === 200 && body && body.item && body.item.quantity === 5
      && body.item.name === 'USB-C Cable 2m (updated)';
    r = await fetch(`${BASE}/api/items/${keptId}`);
    const reget = j(await r.text());
    check('PUT updates and persists (now low stock)',
      putOk && reget && reget.item && reget.item.quantity === 5);

    // 14. PUT invalid -> 400; PUT unknown -> 404
    r = await fetch(`${BASE}/api/items/${keptId}`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({ name: '', category: 'X', quantity: 1, minQuantity: 0 }),
    });
    const badPut = r.status === 400;
    r = await fetch(`${BASE}/api/items/does-not-exist-999`, {
      method: 'PUT', headers: H,
      body: JSON.stringify({ name: 'X', category: 'X', quantity: 1, minQuantity: 0 }),
    });
    check('PUT invalid 400 / unknown 404', badPut && r.status === 404);

    // 15. DELETE -> 204 then 404
    r = await fetch(`${BASE}/api/items/${keptId}`, { method: 'DELETE' });
    const del204 = r.status === 204;
    r = await fetch(`${BASE}/api/items/${keptId}`, { method: 'DELETE' });
    check('DELETE 204 then 404', del204 && r.status === 404);

    // 16. persistence snapshot: record surviving count for the restart phase
    r = await fetch(`${BASE}/api/items`);
    body = j(await r.text());
    check('post-delete total is 10 (restart-phase baseline)',
      r.status === 200 && body && body.total === 10, `total=${body && body.total}`);
    (await import('node:fs')).writeFileSync(
      new URL('./apitest-baseline.json', import.meta.url),
      JSON.stringify({ total: body.total, names: body.items.map(i => i.name) }, null, 2));
  } else {
    // post-restart persistence phase
    let r = await fetch(`${BASE}/api/items`);
    let body = j(await r.text());
    const base = j((await import('node:fs')).readFileSync(
      new URL('./apitest-baseline.json', import.meta.url), 'utf8'));
    check('after server restart: list still 200',
      r.status === 200 && body && Array.isArray(body.items));
    check('after server restart: same 10 items (SQLite persisted)',
      body && body.total === base.total
      && JSON.stringify(body.items.map(i => i.name).sort())
        === JSON.stringify([...base.names].sort()),
      `total=${body && body.total} expected=${base.total}`);
  }

  const passed = results.filter(x => x.pass).length;
  console.log(`\nAPI: ${passed}/${results.length} checks passed (${PHASE} phase)`);
  (await import('node:fs')).writeFileSync(
    new URL(`./apitest-result-${PHASE}.json`, import.meta.url),
    JSON.stringify({ phase: PHASE, passed, total: results.length, results }, null, 2));
  process.exit(passed === results.length ? 0 : 1);
}

main().catch(e => { console.error('SUITE ERROR', e); process.exit(2); });
