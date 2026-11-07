import {chromium} from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
page.on('console', m => console.log('CONSOLE:', m.type(), m.text().slice(0, 150)));
page.on('pageerror', e => console.log('PAGEERROR:', String(e).slice(0, 200)));
page.on('requestfailed', r => console.log('REQFAIL:', r.url().slice(0, 80), r.failure()?.errorText));
page.on('response', r => { if (r.status() >= 400) console.log('HTTP', r.status(), r.url().slice(0, 80)); });
await page.goto('http://127.0.0.1:4173', {waitUntil: 'networkidle'});
await page.waitForTimeout(1500);
console.log('--- initial markup (body, 400 chars) ---');
console.log((await page.content()).slice(0, 400));
// try creating a project
const forms = page.locator('.add-form');
console.log('add-form count:', await forms.count());
if (await forms.count()) {
  await forms.first().locator('input').fill('Debug Project');
  await forms.first().locator('button').first().click();
  await page.waitForTimeout(1500);
  console.log('project-btn count after create:', await page.locator('.project-btn').count());
  console.log('offline-badge:', await page.locator('.offline-badge').count());
}
await browser.close();
