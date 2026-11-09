// RoomReserve screenshots — Session 036 (TRUSTED-SCAFFOLD).
// Real captures from the running application at three viewports + empty.
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';

const BASE = process.env.BASE || 'http://127.0.0.1:3000';
const OUT = process.argv.includes('--out')
  ? process.argv[process.argv.indexOf('--out') + 1]
  : 'shots';

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

async function shot(name, width, height, actions) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  if (actions) await actions(page);
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/roomreserve-${name}.png` });
  await page.screenshot({ path: `${OUT}/roomreserve-${name}-full.png`, fullPage: true });
  console.log(`captured ${name}`);
  await page.close();
}

await shot('desktop-1440x900', 1440, 900);
await shot('mobile-390x844', 390, 844);
await shot('narrow-320x700', 320, 700);

// empty state (wipe rooms via harness reseed-free path: filter to a
// date with no reservations)
await shot('empty-state', 1440, 900, async (page) => {
  await page.locator('input[type="date"]').first().fill('2026-11-20');
  await page.waitForTimeout(800);
});

// re-seed for the live preview
const res = spawnSync('bun', ['run', 'db:reseed-roomreserve'], {
  cwd: '/home/z/my-project', encoding: 'utf8', timeout: 60000,
});
console.log('re-seeded for preview:', res.status === 0);

await browser.close();
