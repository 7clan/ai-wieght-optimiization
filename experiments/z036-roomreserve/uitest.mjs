// RoomReserve frozen UI acceptance test — Session 036.
// FROZEN BEFORE GENERATION (with SPEC.md). 20 ordered Playwright steps.
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
async function reseed() {
  const res = spawnSync('bun', ['run', 'db:reseed-roomreserve'], {
    cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
  });
  return res.status === 0;
}

const D = '2026-11-12';

async function main() {
  const browser = await chromium.launch();
  const pageErrors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => pageErrors.push(String(e)));
  page.on('console', m => {
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) {
      pageErrors.push(m.text());
    }
  });

  // ---- 1. header
  await reseed();
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  check('1. header shows RoomReserve + New Reservation button',
    await page.getByText('RoomReserve', { exact: false }).first().isVisible()
    && await page.getByRole('button', { name: 'New Reservation' }).first().isVisible());

  // ---- 2. rooms panel
  check('2. rooms panel lists 4 seeded rooms with capacity',
    await page.getByText('Atlas Boardroom').first().isVisible()
    && await page.getByText('Breeze Huddle').first().isVisible()
    && await page.getByText('Cove Focus Room').first().isVisible()
    && await page.getByText('Dune Workshop').first().isVisible());

  // ---- 3. reservations for the default listing (confirmed, seeded)
  check('3. reservation list shows seeded confirmed reservations',
    await page.getByText('Quarterly Review').first().isVisible()
    && await page.getByText('Standup').first().isVisible());

  // ---- 4. date filtering
  await page.locator('input[type="date"]').first().fill(D);
  await page.waitForTimeout(600);
  check(`4. date ${D} narrows list to that day (Interview Loop hidden)`,
    await page.getByText('Quarterly Review').first().isVisible()
    && !(await page.getByText('Interview Loop').first().isVisible().catch(() => false)));

  // ---- 5. clear date restores full list
  await page.getByRole('button', { name: /clear date/i }).first().click();
  await page.waitForTimeout(600);
  check('5. Clear date restores full list (Interview Loop visible)',
    await page.getByText('Interview Loop').first().isVisible());

  // ---- 6. room filter
  await page.getByText('Breeze Huddle', { exact: false }).first().click();
  await page.waitForTimeout(600);
  check('6. selecting room filters list (Standup only)',
    await page.getByText('Standup').first().isVisible()
    && !(await page.getByText('Quarterly Review').first().isVisible().catch(() => false)));

  // ---- 7. all rooms reset
  await page.getByRole('button', { name: /all rooms/i }).first().click();
  await page.waitForTimeout(600);
  check('7. All rooms control resets filter',
    await page.getByText('Quarterly Review').first().isVisible());

  // ---- 8. availability filter
  await page.locator('input[type="time"]').first().fill('09:00');
  const times = page.locator('input[type="time"]');
  if (await times.count() > 1) await times.nth(1).fill('10:00');
  await page.waitForTimeout(800);
  const atlasAvail = await page.getByText('Booked', { exact: false })
    .filter({ hasText: /booked/i }).count();
  check('8. availability filter marks Atlas/Breeze booked for 09:00-10:00',
    atlasAvail >= 2,
    `booked-badges=${atlasAvail}`);

  // ---- 9. create dialog opens with labeled fields
  await page.getByRole('button', { name: 'New Reservation' }).first().click();
  for (const label of ['Room', 'Title', 'Organizer', 'Date', 'Start time', 'End time']) {
    const ok = await page.getByLabel(label, { exact: false }).first().isVisible()
      .catch(() => false)
      || await page.getByText(label, { exact: true }).first().isVisible().catch(() => false);
    if (!ok) { check(`9. form dialog labels (${label} missing)`, false); break; }
  }
  check('9. form dialog opens with labels Room/Title/Organizer/Date/Start/End',
    await page.getByLabel('Title', { exact: false }).first().isVisible().catch(() => false)
    || await page.getByText('Title', { exact: true }).first().isVisible().catch(() => false));

  // ---- 10. inline validation on empty submit
  await page.getByRole('button', { name: 'Save Reservation' }).first().click();
  await page.waitForTimeout(400);
  check('10. empty submit shows inline validation, dialog stays open',
    await page.getByText(/required/i).first().isVisible().catch(() => false)
    && await page.getByRole('button', { name: 'Save Reservation' }).first().isVisible());

  // ---- 11. valid create
  const dlg = page.getByRole('dialog').first();
  await dlg.getByLabel('Title', { exact: false }).first().fill('Sprint Demo');
  await dlg.getByLabel('Organizer', { exact: false }).first().fill('Eli Ford');
  const dateIn = dlg.locator('input[type="date"]').first();
  await dateIn.fill(D);
  const t = dlg.locator('input[type="time"]');
  await t.nth(0).fill('16:00');
  await t.nth(1).fill('17:00');
  await page.getByRole('button', { name: 'Save Reservation' }).first().click();
  await page.waitForTimeout(900);
  check('11. valid reservation saved and listed',
    await page.getByText('Sprint Demo').first().isVisible());

  // ---- 12. conflict error inside dialog
  await page.getByRole('button', { name: 'New Reservation' }).first().click();
  const dlg2 = page.getByRole('dialog').first();
  await dlg2.getByLabel('Title', { exact: false }).first().fill('Clash');
  await dlg2.getByLabel('Organizer', { exact: false }).first().fill('Eli Ford');
  await dlg2.locator('input[type="date"]').first().fill(D);
  const t2 = dlg2.locator('input[type="time"]');
  await t2.nth(0).fill('09:30');
  await t2.nth(1).fill('10:00');
  await page.getByRole('button', { name: 'Save Reservation' }).first().click();
  await page.waitForTimeout(900);
  check('12. overlapping booking shows conflict message in dialog',
    await page.getByText('Time conflict with an existing reservation')
      .first().isVisible());

  // ---- 13. Escape closes dialog (keyboard)
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  check('13. Escape closes the dialog',
    !(await page.getByRole('dialog').first().isVisible().catch(() => false)));

  // ---- 14. edit flow
  const row = page.locator('tr', { hasText: 'Sprint Demo' }).first();
  if (!(await row.count())) {
    check('14. edit: row exists', false);
  } else {
    await row.getByRole('button', { name: /edit/i }).first().click();
    await page.waitForTimeout(500);
    const dlg3 = page.getByRole('dialog').first();
    await dlg3.getByLabel('Title', { exact: false }).first().fill('Sprint Demo v2');
    await page.getByRole('button', { name: 'Save Reservation' }).first().click();
    await page.waitForTimeout(900);
    check('14. edit saves (Sprint Demo v2 listed)',
      await page.getByText('Sprint Demo v2').first().isVisible());
  }

  // ---- 15. cancel with confirmation
  const row2 = page.locator('tr', { hasText: 'Sprint Demo v2' }).first();
  if (!(await row2.count())) {
    check('15. cancel: row exists', false);
  } else {
    await row2.getByRole('button', { name: /cancel/i }).first().click();
    await page.waitForTimeout(400);
    const confirm = page.getByRole('button', { name: /^confirm$/i }).first();
    const confirmVisible = await confirm.isVisible().catch(() => false);
    if (confirmVisible) await confirm.click();
    await page.waitForTimeout(900);
    check('15. cancel asks confirmation then removes row from default list',
      confirmVisible
      && !(await page.getByText('Sprint Demo v2').first().isVisible().catch(() => false)));
  }

  // ---- 16. show cancelled toggle reveals Cancelled badge
  await page.getByRole('button', { name: /show cancelled/i }).first().click();
  await page.waitForTimeout(700);
  check('16. Show cancelled reveals Cancelled badge',
    await page.getByText('Cancelled', { exact: false }).first().isVisible());

  // ---- 17. error state + retry (API outage via interception)
  await page.route('**/api/reservations**', route => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 500, body: 'boom' });
    }
    return route.continue();
  });
  await page.reload({ waitUntil: 'networkidle' });
  const retryVisible = await page.getByRole('button', { name: /retry/i })
    .first().isVisible().catch(() => false);
  const errorPanel = await page.getByText(/something went wrong|failed to load|error/i)
    .first().isVisible().catch(() => false);
  check('17. API outage -> error panel with Retry', retryVisible && errorPanel,
    `retry=${retryVisible} panel=${errorPanel}`);
  await page.unroute('**/api/reservations**');
  await page.getByRole('button', { name: /retry/i }).first().click();
  await page.waitForTimeout(900);
  check('18. Retry recovers the list',
    await page.getByText('Quarterly Review').first().isVisible());

  // ---- 19. mobile 390 no overflow
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(700);
  const overflow390 = await page.evaluate(
    () => document.documentElement.scrollWidth
      - document.documentElement.clientWidth);
  check('19. 390px: no horizontal overflow', overflow390 <= 0, `overflow=${overflow390}px`);

  // ---- 20. narrow 320 + persistence via reload
  await page.setViewportSize({ width: 320, height: 700 });
  await page.waitForTimeout(500);
  const overflow320 = await page.evaluate(
    () => document.documentElement.scrollWidth
      - document.documentElement.clientWidth);
  await page.reload({ waitUntil: 'networkidle' });
  check('20. 320px no overflow + data persists after reload',
    overflow320 <= 0
    && await page.getByText('Quarterly Review').first().isVisible(),
    `overflow=${overflow320}px`);

  await browser.close();
  const summary = results.filter(x => x.pass).length;
  const pageErrCount = pageErrors.length;
  console.log(`\npageErrors: ${pageErrCount}`);
  console.log(`UI: ${summary}/${n} checks passed`);
  process.exit(summary === n && pageErrCount === 0 ? 0 : 1);
}

main().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
