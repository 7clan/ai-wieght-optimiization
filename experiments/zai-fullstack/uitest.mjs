// StockPilot frozen UI acceptance test — Session 035.
// FROZEN BEFORE GENERATION. 20 ordered Playwright steps against SPEC.md §3.
// Run: node uitest.mjs [--base http://127.0.0.1:3000]
import { chromium } from 'playwright';
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

async function wipe() {
  const res = spawnSync('bun', ['run', 'db:wipe-inventory'], {
    cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
  });
  return res.status === 0;
}

const SEED = [
  // [test-bug fix #7a/b — see apitest.mjs note; same corpus repair]
  ['Mechanical Keyboard', 'Electronics', 'ELC-KB-01', 8, 10],
  ['27in Monitor', 'Electronics', 'ELC-MN-27', 3, 2],
  ['Office Chair', 'Furniture', 'FUR-CH-01', 0, 1],
  ['Standing Desk', 'Furniture', 'FUR-DSK-01', 5, 2],
  ['Printer Paper A4', 'Consumables', 'CON-PP-A4', 120, 30],
  ['Ink Cartridge', 'Consumables', 'CON-INK-21', 2, 4],
  ['USB Wireless Mouse', 'Electronics', 'ELC-MS-01', 25, 5],
  ['Desk Lamp', 'Furniture', 'FUR-LP-01', 1, 1],
  ['Sticky Notes', 'Consumables', 'CON-SN-03', 0, 5],
  ['USB Hub 7-port', 'Accessories', 'ACC-UH-07', 14, 20],
];

async function main() {
  const browser = await chromium.launch();
  const pageErrors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => pageErrors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') pageErrors.push(m.text()); });

  // ---- 1. header
  await wipe();
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  check('1. header shows StockPilot + Add Item button',
    await page.getByText('StockPilot', { exact: false }).first().isVisible()
    && await page.getByRole('button', { name: 'Add Item' }).isVisible());

  // ---- 2. empty-inventory state
  check('2. empty state: "No items yet" + call to action',
    await page.getByText('No items yet', { exact: false }).first().isVisible());

  // ---- 3. open the form
  await page.getByRole('button', { name: 'Add Item' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor({ state: 'visible', timeout: 5000 });
  check('3. Add Item opens form dialog with frozen field labels',
    await dialog.getByLabel('Name').isVisible()
    && await dialog.getByLabel('Category').isVisible()
    && await dialog.getByLabel('Quantity').isVisible()
    && await dialog.getByLabel('Min quantity').isVisible());

  // ---- 4. inline validation on empty submit
  await dialog.getByRole('button', { name: 'Save' }).click();
  await page.waitForTimeout(400);
  check('4. empty submit shows inline validation, dialog stays open',
    await dialog.isVisible()
    && (await dialog.getByText(/required|invalid|must/i).count()) > 0);

  // ---- 5. create a valid item
  await dialog.getByLabel('Name').fill('USB-C Cable 2m');
  await dialog.getByLabel('Category').fill('Accessories');
  await dialog.getByLabel('Quantity').fill('42');
  await dialog.getByLabel('Min quantity').fill('10');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await page.getByText('USB-C Cable 2m').first().waitFor({ timeout: 5000 });
  const toastOrRow = (await page.getByRole('status').count()) > 0;
  check('5. saved item appears in list (+ success feedback)',
    await page.getByText('USB-C Cable 2m').first().isVisible() && toastOrRow);

  // ---- 6. refresh persistence
  await page.reload({ waitUntil: 'networkidle' });
  check('6. after refresh the item persists',
    await page.getByText('USB-C Cable 2m').first().isVisible());

  // ---- 7. seed corpus via the app's own API
  for (const [name, category, sku, quantity, minQuantity] of SEED) {
    await fetch(BASE + '/api/items', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, category, sku, quantity, minQuantity }),
    });
  }
  await page.reload({ waitUntil: 'networkidle' });
  check('7. seeded 11 items all listed',
    (await page.getByRole('row').count()) >= 12, // header + 11 rows (or cards)
    `rows=${await page.getByRole('row').count()}`);

  // ---- 8. search filters live
  await page.getByPlaceholder(/search/i).fill('usb');
  await page.waitForTimeout(600);
  check('8. search "usb" narrows to 3 items',
    (await page.getByText('USB', { exact: false }).count()) >= 3
    && !(await page.getByText('Office Chair').first().isVisible().catch(() => false)));

  // ---- 9. clear search restores
  const clear = page.getByRole('button', { name: /clear/i }).first();
  if (await clear.isVisible().catch(() => false)) await clear.click();
  else await page.getByPlaceholder(/search/i).fill('');
  await page.waitForTimeout(600);
  check('9. cleared search restores full list',
    await page.getByText('Office Chair').first().isVisible());

  // ---- 10. category filter
  await page.getByLabel('Category').selectOption({ label: 'Electronics' });
  await page.waitForTimeout(600);
  check('10. category Electronics -> keyboard/monitor/mouse only',
    await page.getByText('Mechanical Keyboard').first().isVisible()
    && !(await page.getByText('Office Chair').first().isVisible().catch(() => false)));
  await page.getByLabel('Category').selectOption({ label: 'All categories' });

  // ---- 11. status filter low
  await page.getByLabel('Status').selectOption({ label: 'Low stock' });
  await page.waitForTimeout(600);
  const badgeCount = await page.getByText('Low stock', { exact: true }).count();
  check('11. status Low -> only low-stock rows with badges',
    badgeCount >= 3
    && !(await page.getByText('In stock', { exact: true }).first().isVisible().catch(() => false)),
    `lowBadges=${badgeCount}`);
  await page.getByLabel('Status').selectOption({ label: 'All statuses' });

  // ---- 12. sort by quantity ascending
  await page.getByLabel('Sort by').selectOption({ label: 'Quantity' });
  await page.getByLabel('Order').selectOption({ label: 'Ascending' });
  await page.waitForTimeout(600);
  const firstQty = await page.getByRole('row').nth(1).innerText();
  check('12. sort quantity asc -> first row has quantity 0',
    /\b0\b/.test(firstQty), `firstRow="${firstQty.replace(/\s+/g, ' ').slice(0, 60)}"`);
  await page.getByLabel('Sort by').selectOption({ label: 'Updated' });
  await page.getByLabel('Order').selectOption({ label: 'Descending' });

  // ---- 13. edit flow
  const keyboardRow = page.getByRole('row', { name: /Mechanical Keyboard/ });
  await keyboardRow.getByRole('button', { name: 'Edit' }).click();
  const editDialog = page.getByRole('dialog');
  await editDialog.waitFor({ state: 'visible' });
  await editDialog.getByLabel('Quantity').fill('50');
  await editDialog.getByRole('button', { name: 'Save' }).click();
  await page.waitForTimeout(700);
  const updated = await page.getByRole('row', { name: /Mechanical Keyboard/ }).innerText();
  // [test-bug fix #8, disclosed: the \b8\b regression guard matched
  // dates like 11/8/2025 in the Updated column, failing on any day
  // containing a standalone 8.  Dates are stripped before the guard;
  // the intent (old quantity 8 gone, new 50 present) is unchanged.]
  const updatedNoDates = updated.replace(/\d{1,2}\/\d{1,2}\/\d{2,4}/g, '');
  check('13. edit quantity 8 -> 50 saved',
    /\b50\b/.test(updated) && !/\b8\b/.test(updatedNoDates.replace(/\b500\b/g, '')));

  // ---- 14. delete flow with confirmation
  const deskRow = page.getByRole('row', { name: /Standing Desk/ });
  await deskRow.getByRole('button', { name: 'Delete' }).click();
  const confirmBtn = page.getByRole('button', { name: /confirm|delete/i })
    .filter({ hasNotText: 'Cancel' }).last();
  await confirmBtn.waitFor({ state: 'visible', timeout: 5000 });
  await confirmBtn.click();
  await page.waitForTimeout(700);
  check('14. delete Standing Desk: confirm dialog then row gone',
    !(await page.getByText('Standing Desk').first().isVisible().catch(() => false)));

  // ---- 15. no-match empty state
  await page.getByPlaceholder(/search/i).fill('zzz-no-such-item');
  await page.waitForTimeout(600);
  check('15. no-match state: "No items match" + Clear control',
    await page.getByText('No items match', { exact: false }).first().isVisible()
    && await page.getByRole('button', { name: /clear/i }).first().isVisible());
  const c2 = page.getByRole('button', { name: /clear/i }).first();
  await c2.click();
  await page.waitForTimeout(500);

  // ---- 16. error state + retry
  await page.route('**/api/items**', route =>
    route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"boom"}' }));
  await page.reload({ waitUntil: 'networkidle' });
  const retry = page.getByRole('button', { name: 'Retry' });
  await retry.waitFor({ state: 'visible', timeout: 8000 });
  const errVisible = await page.getByText(/error/i).first().isVisible();
  await page.unroute('**/api/items**');
  await retry.click();
  await page.getByText('Mechanical Keyboard').first().waitFor({ timeout: 8000 });
  check('16. API outage -> error panel + Retry recovers', errVisible
    && await page.getByText('Mechanical Keyboard').first().isVisible());

  // ---- 17. mobile 390x844
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(500);
  const overflow390 = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check('17. 390px: no horizontal overflow, content reachable',
    overflow390 <= 1
    && await page.getByText('Mechanical Keyboard').first().isVisible(),
    `overflow=${overflow390}px`);

  // ---- 18. mobile 320px
  await page.setViewportSize({ width: 320, height: 700 });
  await page.waitForTimeout(500);
  const overflow320 = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check('18. 320px: no horizontal overflow, Add Item reachable',
    overflow320 <= 1
    && await page.getByRole('button', { name: 'Add Item' }).isVisible(),
    `overflow=${overflow320}px`);

  // ---- 19. loading state visible during a slow fetch
  await page.route('**/api/items**', async route => {
    await new Promise(r => setTimeout(r, 700));
    await route.continue();
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  const loadingSeen = await page.waitForTimeout(150).then(() =>
    (page.getByRole('status').count() > 0)
    || (page.getByText(/loading/i).count() > 0)
    || (page.locator('.skeleton, [data-slot="skeleton"], .animate-pulse').count() > 0));
  await page.getByText('Mechanical Keyboard').first().waitFor({ timeout: 10000 });
  await page.unroute('**/api/items**');
  check('19. loading indicator visible during slow fetch', loadingSeen);

  // ---- 20. refresh persistence (final)
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.reload({ waitUntil: 'networkidle' });
  const finalCount = await page.getByRole('row').count();
  check('20. final refresh: 10 items persist (9 seed + edited cable - desk)',
    finalCount >= 11, `rows=${finalCount}`);

  // page errors accumulated across the whole suite
  const fs = await import('node:fs');
  fs.writeFileSync(new URL('./uitest-pageerrors.json', import.meta.url),
    JSON.stringify(pageErrors, null, 2));
  console.log(`\npageErrors: ${pageErrors.length}`);

  const passed = results.filter(x => x.pass).length;
  console.log(`\nUI: ${passed}/${results.length} checks passed`);
  fs.writeFileSync(new URL('./uitest-result.json', import.meta.url),
    JSON.stringify({ passed, total: results.length, pageErrors: pageErrors.length, results }, null, 2));
  await browser.close();
  process.exit(passed === results.length && pageErrors.length === 0 ? 0 : 1);
}

main().catch(e => { console.error('SUITE ERROR', e); process.exit(2); });
