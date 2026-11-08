// StockPilot real-browser screenshots — Session 035 (TRUSTED-SCAFFOLD).
// Captures the live app at the three frozen viewports, with data.
// Run: node shots.mjs [--base http://127.0.0.1:3000] [--out shots]
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const arg = (n, d) => {
  const i = process.argv.indexOf('--' + n);
  return i > -1 ? process.argv[i + 1] : d;
};
const BASE = arg('base', process.env.BASE || 'http://127.0.0.1:3000');
const OUT = new URL('./' + (arg('out', 'shots') + '/'), import.meta.url).pathname;

const SEED = [
  ['Mechanical Keyboard', 'Electronics', 'ELC-KB-01', 8, 10],
  ['27in Monitor', 'Electronics', 'ELC-MN-27', 3, 2],
  ['Office Chair', 'Furniture', 'FUR-CH-01', 0, 1],
  ['Standing Desk', 'Furniture', 'FUR-DSK-01', 5, 2],
  ['Printer Paper A4', 'Consumables', 'CON-PP-A4', 120, 30],
  ['Ink Cartridge', 'Consumables', 'CON-INK-21', 2, 4],
  ['Wireless Mouse', 'Electronics', 'ELC-MS-01', 25, 5],
  ['Desk Lamp', 'Furniture', 'FUR-LP-01', 1, 1],
  ['Sticky Notes', 'Consumables', 'CON-SN-03', 0, 5],
  ['USB Hub 7-port', 'Accessories', 'ACC-UH-07', 14, 6],
];

async function main() {
  mkdirSync(OUT, { recursive: true });
  // ensure data exists (idempotent seed)
  const list = await (await fetch(`${BASE}/api/items`)).json();
  if (!list.total) {
    for (const [name, category, sku, quantity, minQuantity] of SEED) {
      await fetch(`${BASE}/api/items`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, category, sku, quantity, minQuantity }),
      });
    }
    console.log('seeded', SEED.length, 'items');
  }

  const browser = await chromium.launch();
  for (const [w, h, name] of [
    [1440, 900, 'desktop-1440x900'],
    [390, 844, 'mobile-390x844'],
    [320, 700, 'narrow-320x700'],
  ]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(BASE + '/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/stockpilot-${name}.png`, fullPage: false });
    await page.screenshot({ path: `${OUT}/stockpilot-${name}-full.png`, fullPage: true });
    console.log(`captured ${name}`);
    await page.close();
  }

  // empty state (wipe via the harness script, then reload)
  const { spawnSync } = await import('node:child_process');
  spawnSync('bun', ['run', 'db:wipe-inventory'], {
    cwd: '/home/z/my-project', timeout: 60000,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/stockpilot-empty-state.png` });
  console.log('captured empty state');

  // restore seed data for the preview
  for (const [name, category, sku, quantity, minQuantity] of SEED) {
    await fetch(`${BASE}/api/items`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, category, sku, quantity, minQuantity }),
    });
  }
  console.log('re-seeded for preview');
  await browser.close();
}
main().catch(e => { console.error(e); process.exit(1); });
