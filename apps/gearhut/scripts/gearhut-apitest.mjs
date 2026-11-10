// SESSION040 GearHut — Phase-6 API test suite (frozen test plan in
// APP_SPEC.json §test_plan_phase6.api). TRUSTED test code, not model output.
// Run against the live dev server: node scripts/gearhut-apitest.mjs
const BASE = 'http://localhost:3000'

let passed = 0
let failed = 0
const failures = []

async function check(name, condition, detail = '') {
  if (condition) { passed++; console.log(`  ok ${name}`) }
  else { failed++; failures.push(name + (detail ? ` — ${detail}` : '')); console.log(`  FAIL ${name} ${detail}`) }
}

async function j(url, init) {
  const response = await fetch(BASE + url, init)
  let body = null
  try { body = await response.json() } catch { /* 204 etc. */ }
  return { status: response.status, body }
}

async function main() {
  console.log('GET phase')
  const all = await j('/api/gearhut-items')
  await check('get-no-params-200', all.status === 200)
  await check('get-envelope-gear-total', Array.isArray(all.body?.gear) && typeof all.body?.total === 'number')
  await check('get-seeded-nonempty', all.body.gear.length >= 5, `got ${all.body?.gear?.length}`)
  const aurora = all.body.gear.find(r => r.label === 'Aurora tent')
  await check('get-row-fields', aurora && typeof aurora.usageHours === 'number' && typeof aurora.status === 'string')
  const labels = all.body.gear.map(r => r.label)
  await check('get-ordered-by-label', JSON.stringify(labels) === JSON.stringify([...labels].sort()), labels.join(','))

  const search = await j('/api/gearhut-items?search=TERRA')
  await check('get-search-case-insensitive', search.status === 200
    && search.body.gear.length === 1 && search.body.gear[0].label === 'Terra 40 backpack'
    && search.body.total === 1, JSON.stringify(search.body?.gear?.map(r => r.label)))

  const status = await j('/api/gearhut-items?status=inspected')
  await check('get-status-exact', status.body.gear.length === 2
    && status.body.gear.every(r => r.status === 'inspected'), `got ${status.body?.gear?.length}`)

  const combined = await j('/api/gearhut-items?search=canyon&status=stashed')
  await check('get-combined-filters', combined.body.gear.length === 1
    && combined.body.gear[0].label === 'Canyon rope 60m')

  const allFilter = await j('/api/gearhut-items?status=all')
  await check('get-status-all-no-filter', allFilter.body.gear.length === all.body.gear.length)

  const none = await j('/api/gearhut-items?search=zzzznothing')
  await check('get-no-match-empty', none.body.gear.length === 0 && none.body.total === 0)

  console.log('POST phase')
  const created = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: 'Test harness carabiner', usageHours: 3, lockerId: 'locker-main' }),
  })
  await check('post-valid-201', created.status === 201, `got ${created.status}`)
  await check('post-created-status-stashed', created.body?.status === 'stashed')
  await check('post-created-fields', created.body?.id && created.body?.label === 'Test harness carabiner')
  const reread = await j('/api/gearhut-items?search=harness carabiner')
  await check('post-persisted', reread.body.gear.length === 1, 'row not found after POST')

  const missing = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ usageHours: 3, lockerId: 'locker-main' }),
  })
  await check('post-missing-label-400', missing.status === 400 && typeof missing.body?.error === 'string')

  const blank = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: '   ', usageHours: 3, lockerId: 'locker-main' }),
  })
  await check('post-blank-label-400', blank.status === 400)

  const range = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: 'Over-range item', usageHours: 3000, lockerId: 'locker-main' }),
  })
  await check('post-usage-out-of-range-400', range.status === 400)

  const frac = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: 'Fractional item', usageHours: 2.5, lockerId: 'locker-main' }),
  })
  await check('post-usage-non-integer-400', frac.status === 400)

  const bogus = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: 'Bogus locker item', usageHours: 3, lockerId: 'no-such-locker' }),
  })
  await check('post-bogus-locker-404', bogus.status === 404)

  const dup = await j('/api/gearhut-items', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: 'Aurora tent', usageHours: 3, lockerId: 'locker-main' }),
  })
  await check('post-duplicate-label-409', dup.status === 409)

  console.log('PATCH phase (invariant load-bearing)')
  const stashed = (await j('/api/gearhut-items?status=stashed')).body.gear[0]
  const legal = await j(`/api/gearhut-items/${stashed.id}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ status: 'inspected' }),
  })
  await check('patch-legal-advance-200', legal.status === 200 && legal.body?.status === 'inspected',
    `got ${legal.status}`)

  const retired = (await j('/api/gearhut-items?status=retired')).body.gear[0]
  const illegal = await j(`/api/gearhut-items/${retired.id}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ status: 'stashed' }),
  })
  await check('patch-retired-backward-409', illegal.status === 409 && typeof illegal.body?.error === 'string')

  const skipAhead = await j(`/api/gearhut-items/${stashed.id}`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ status: 'retired' }),
  })
  await check('patch-skip-stage-409', skipAhead.status === 409)

  console.log('DELETE phase')
  const victim = (await j('/api/gearhut-items?search=harness carabiner')).body.gear[0]
  const deleted = await fetch(`${BASE}/api/gearhut-items/${victim.id}`, { method: 'DELETE' })
  await check('delete-204', deleted.status === 204, `got ${deleted.status}`)
  const gone = await j('/api/gearhut-items?search=harness carabiner')
  await check('delete-row-gone', gone.body.gear.length === 0)

  console.log(`\nAPI suite: ${passed} passed, ${failed} failed`)
  if (failures.length) { console.log('failures:\n  ' + failures.join('\n  ')); process.exit(1) }
}

main().catch((error) => { console.error(error); process.exit(1) })
