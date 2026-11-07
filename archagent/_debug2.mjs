import {chromium} from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
page.on('console', m => console.log('CONSOLE:', m.type(), m.text().slice(0, 120)));
page.on('pageerror', e => console.log('PAGEERROR:', String(e).slice(0, 200)));
await page.goto('http://127.0.0.1:4173', {waitUntil: 'networkidle', timeout: 15000});
await page.waitForSelector('.app', {timeout: 8000});
const forms = page.locator('.add-form');
const projForm = forms.first();
await projForm.locator('input').fill('Website Redesign');
await projForm.locator('button[type=submit], button').first().click();
try {
  await page.waitForSelector('.project-btn', {timeout: 6000});
  console.log('STEP2: project-btn appeared');
} catch (e) {
  console.log('STEP2 FAIL:', String(e).split('\n')[0]);
  console.log('body now:', (await page.content()).slice(0, 300));
}
await browser.close();
