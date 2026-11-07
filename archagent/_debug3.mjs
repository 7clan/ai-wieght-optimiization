import {chromium} from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('http://127.0.0.1:4173', {waitUntil: 'networkidle'});
await page.waitForSelector('.app');
const info = await page.evaluate(() => {
  const btn = document.querySelector('.project-btn');
  if (!btn) return {exists: false};
  const cs = getComputedStyle(btn);
  const r = btn.getBoundingClientRect();
  return {exists: true, display: cs.display, visibility: cs.visibility,
          width: r.width, height: r.height,
          parentDisplay: getComputedStyle(btn.parentElement).display,
          appDisplay: getComputedStyle(document.querySelector('.app')).display,
          bodyHtml: document.body.innerHTML.slice(0, 150)};
});
console.log(JSON.stringify(info, null, 1));
await browser.close();
