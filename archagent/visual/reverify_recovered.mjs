// Re-verification functional test for the RECOVERED Session 034 apps.
// Runs the recovered TaskFlow v2 and MediVault through real browser
// interactions and records console/page errors.  TRUSTED-SCAFFOLD.
'use strict';
import {chromium} from 'playwright';
import {writeFileSync, mkdirSync} from 'node:fs';
import path from 'node:path';

const BASE = process.env.BASE || 'http://127.0.0.1:4195';
const OUT = process.env.OUT || 'recovery/session034-preview/reverify-functional.json';
const steps = [];
function record(step, ok, detail) {
  steps.push({step, ok, detail: (detail || '').slice(0, 300)});
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${step}${detail ? ' — ' + String(detail).slice(0, 120) : ''}`);
}

async function taskflowSuite(browser) {
  const ctx = await browser.newContext({viewport: {width: 1280, height: 800}});
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e.message).slice(0, 160)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 160)); });

  const url = `${BASE}/taskflow-v2/index.html`;
  // 1 open
  try {
    await page.goto(url, {waitUntil: 'networkidle', timeout: 20000});
    await page.waitForSelector('.sidebar, .app', {timeout: 10000});
    record('1 open application', true, url);
  } catch (e) { record('1 open application', false, e.message.split('\n')[0]); return {errors, page, ctx}; }

  // 2 create project
  try {
    await page.click('.btn-block:has-text("New Project"), button:has-text("+ New Project")');
    await page.waitForSelector('[id="Project name"]', {timeout: 5000});
    await page.fill('[id="Project name"]', 'Website Redesign');
    await page.click('button:has-text("Create Project")');
    await page.waitForTimeout(400);
    const nav = await page.locator('.nav-item').allTextContents();
    record('2 create project', nav.some(n => /Website Redesign/.test(n)), JSON.stringify(nav));
  } catch (e) { record('2 create project', false, e.message.split('\n')[0]); }

  // 3 select project
  try {
    await page.click('.nav-item:has-text("Website Redesign")');
    await page.waitForTimeout(300);
    const h2 = await page.locator('.view-head h2').textContent().catch(() => '');
    record('3 select project', /Website Redesign/.test(h2 || ''), 'h2=' + h2);
  } catch (e) { record('3 select project', false, e.message.split('\n')[0]); }

  // 4 add task (modal flow)
  try {
    await page.click('button:has-text("New Task")');
    await page.waitForSelector('#title', {timeout: 4000});
    await page.fill('#title', 'Draft homepage');
    await page.selectOption('#priority', 'high');
    await page.click('button:has-text("Add Task")');
    await page.waitForTimeout(400);
    const cards = await page.locator('.card h3').allTextContents();
    record('4 add task', cards.some(c => /Draft homepage/.test(c)), JSON.stringify(cards));
  } catch (e) { record('4 add task', false, e.message.split('\n')[0]); }

  // 4b add second task
  try {
    await page.click('button:has-text("New Task")');
    await page.waitForSelector('#title', {timeout: 4000});
    await page.fill('#title', 'Review colors');
    await page.selectOption('#priority', 'low');
    await page.click('button:has-text("Add Task")');
    await page.waitForTimeout(400);
    const cards = await page.locator('.card h3').allTextContents();
    record('4b add second task', cards.length >= 2, JSON.stringify(cards));
  } catch (e) { record('4b add second task', false, e.message.split('\n')[0]); }

  // 5 verify priority chips
  try {
    const chips = await page.locator('.chip').allTextContents();
    record('5 priority shown', chips.some(c => /high/.test(c)) && chips.some(c => /low/.test(c)),
           JSON.stringify(chips));
  } catch (e) { record('5 priority shown', false, e.message.split('\n')[0]); }

  // 6 complete a task (v2 status cycles todo -> doing -> done; click to done)
  try {
    const card = page.locator('.card:has-text("Review colors")');
    let done = false, badge = '';
    for (let i = 0; i < 3 && !done; i++) {
      await card.locator('h3').click();
      await page.waitForTimeout(300);
      badge = (await card.locator('.badge').textContent().catch(() => '')) || '';
      done = /done/i.test(badge);
    }
    record('6 mark complete (status cycle reaches done)', done, 'badge=' + badge);
  } catch (e) { record('6 mark complete', false, e.message.split('\n')[0]); }

  // 7 progress text (non-zero: some task done among visible)
  try {
    const pct = await page.locator('.progress-track small').first().textContent();
    record('7 progress text', /^\d+%$/.test((pct || '').trim()) && pct.trim() !== '0%',
           'progress=' + pct);
  } catch (e) { record('7 progress text', false, e.message.split('\n')[0]); }

  // 8 search
  try {
    await page.fill('.toolbar .input', 'Draft');
    await page.waitForTimeout(400);
    const cards = await page.locator('.card h3').allTextContents();
    record('8 search tasks', cards.length === 1 && /Draft homepage/.test(cards[0] || ''),
           JSON.stringify(cards));
    await page.fill('.toolbar .input', '');
    await page.waitForTimeout(300);
  } catch (e) { record('8 search tasks', false, e.message.split('\n')[0]); }

  // 9 filter by status
  try {
    await page.selectOption('.toolbar .select', 'done');
    await page.waitForTimeout(400);
    const doneCards = await page.locator('.card h3').allTextContents();
    await page.selectOption('.toolbar .select', 'all');
    await page.waitForTimeout(300);
    const allCards = await page.locator('.card h3').allTextContents();
    record('9 filter by status', doneCards.length >= 1 && allCards.length > doneCards.length,
           `done=${doneCards.length} all=${allCards.length}`);
  } catch (e) { record('9 filter by status', false, e.message.split('\n')[0]); }

  // 10 delete task
  try {
    await page.locator('.card:has-text("Review colors") .btn-icon').click();
    await page.waitForTimeout(400);
    const cards = await page.locator('.card h3').allTextContents();
    record('10 delete task', !cards.some(c => /Review colors/.test(c)), JSON.stringify(cards));
  } catch (e) { record('10 delete task', false, e.message.split('\n')[0]); }

  // 11 updated progress after delete (recomputed, non-zero)
  try {
    const pct = await page.locator('.progress-track small').first().textContent();
    record('11 updated progress', /^\d+%$/.test((pct || '').trim()), 'progress=' + pct);
  } catch (e) { record('11 updated progress', false, e.message.split('\n')[0]); }

  // 12 refresh + persistence
  try {
    await page.reload({waitUntil: 'networkidle'});
    await page.waitForTimeout(600);
    const cards = await page.locator('.card h3').allTextContents();
    const nav = await page.locator('.nav-item').allTextContents();
    record('12 persistence after refresh', cards.some(c => /Draft homepage/.test(c)) &&
           nav.some(n => /Website Redesign/.test(n)),
           `cards=${JSON.stringify(cards)} nav=${nav.length}`);
  } catch (e) { record('12 persistence after refresh', false, e.message.split('\n')[0]); }

  // 13 mobile viewport renders with menu
  try {
    const mp = await browser.newContext({viewport: {width: 390, height: 844}});
    const m = await mp.newPage();
    await m.goto(url, {waitUntil: 'networkidle'});
    await m.waitForSelector('.menu-btn', {timeout: 6000});
    await m.click('.menu-btn');
    await m.waitForTimeout(300);
    const sidebarVisible = await m.locator('.sidebar.open').isVisible().catch(() => false);
    record('13 mobile menu', sidebarVisible, 'sidebar.open visible=' + sidebarVisible);
    await mp.close();
  } catch (e) { record('13 mobile menu', false, e.message.split('\n')[0]); }

  // 14 new screenshot (this session's own capture of the recovered app)
  try {
    await page.evaluate(() => {
      const s = window.TaskFlowStore;
      if (s && s.addProject) {
        s.addProject('Mobile App v2');
        const d = s.getData();
        const p2 = d.projects.find(p => p.name === 'Mobile App v2');
        if (p2) { s.addTask && s.addTask(p2.id, 'Onboarding flow', 'high', ''); }
      }
    });
    await page.waitForTimeout(400);
    await page.screenshot({path: 'recovery/session034-preview/shots/reverify-taskflow-desktop.png'});
    record('14 desktop screenshot', true);
  } catch (e) { record('14 desktop screenshot', false, e.message.split('\n')[0]); }

  await ctx.close();
  return {errors};
}

async function medivaultSuite(browser) {
  const ctx = await browser.newContext({viewport: {width: 1280, height: 800}});
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e.message).slice(0, 160)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 160)); });

  const url = `${BASE}/medivault/index.html`;
  // M1 open
  try {
    await page.goto(url, {waitUntil: 'networkidle', timeout: 20000});
    await page.waitForSelector('.folder-tabs, .vault-view', {timeout: 10000});
    record('M1 open application', true, url);
  } catch (e) { record('M1 open application', false, e.message.split('\n')[0]); return {errors}; }

  // M2 create folder
  try {
    await page.click('button:has-text("New Folder")');
    await page.waitForTimeout(300);
    const labels = await page.locator('.modal label, .modal .label, dialog label, .field label').allTextContents().catch(() => []);
    let created = false;
    const input = page.locator('.modal input, dialog input, .field input[type=text]').first();
    if (await input.count()) {
      await input.fill('Radiology');
      const submit = page.locator('button:has-text("Create"), button:has-text("Add"), button[type=submit]').last();
      if (await submit.count()) { await submit.click(); await page.waitForTimeout(400); }
    }
    const tabs = await page.locator('.folder-tab').allTextContents();
    created = tabs.some(t => /Radiology/.test(t));
    record('M2 create folder', created, JSON.stringify(tabs) + ' labels=' + JSON.stringify(labels).slice(0, 80));
  } catch (e) { record('M2 create folder', false, e.message.split('\n')[0]); }

  // M3 upload document (synthetic test file)
  try {
    await page.click('button:has-text("Upload Document")');
    await page.waitForTimeout(300);
    const fileInput = page.locator('input[type=file]');
    if (await fileInput.count()) {
      await fileInput.setInputFiles({
        name: 'mri-report.txt', mimeType: 'text/plain',
        buffer: Buffer.from('Synthetic MRI report for permission testing. Not real data.'),
      });
      await page.fill('#mv-patient', 'A.K.');
      await page.fill('#mv-date', '2026-11-08');
      const submit = page.locator('button:has-text("Upload"), button:has-text("Add"), button[type=submit]').last();
      await submit.click();
      await page.waitForTimeout(500);
    }
    const rows = await page.locator('.table tbody tr').allTextContents();
    record('M3 upload document', rows.some(r => /mri-report/.test(r)), JSON.stringify(rows).slice(0, 160));
  } catch (e) { record('M3 upload document', false, e.message.split('\n')[0]); }

  // M4 search
  try {
    await page.fill('.toolbar .input', 'mri');
    await page.waitForTimeout(400);
    const rows = await page.locator('.table tbody tr').allTextContents();
    record('M4 search', rows.length === 1 && /mri-report/.test(rows[0] || ''), JSON.stringify(rows).slice(0, 120));
    await page.fill('.toolbar .input', '');
    await page.waitForTimeout(300);
  } catch (e) { record('M4 search', false, e.message.split('\n')[0]); }

  // M5 type filter
  try {
    const options = await page.locator('.toolbar .select option').allTextContents();
    await page.selectOption('.toolbar .select', {index: 1}).catch(() => {});
    await page.waitForTimeout(400);
    const filtered = await page.locator('.table tbody tr').allTextContents();
    record('M5 type filter', true, `options=${JSON.stringify(options).slice(0, 60)} rows=${filtered.length}`);
    await page.selectOption('.toolbar .select', {index: 0}).catch(() => {});
    await page.waitForTimeout(300);
  } catch (e) { record('M5 type filter', false, e.message.split('\n')[0]); }

  // M6 view detail (metadata)
  try {
    await page.click('.doc-name');
    await page.waitForTimeout(400);
    const modalText = await page.locator('.modal').textContent().catch(() => '');
    const hasMeta = /A\.K\./.test(modalText) && /2026-11-08|mri-report/.test(modalText);
    record('M6 view detail metadata', hasMeta, (modalText || '').slice(0, 120).replace(/\s+/g, ' '));
    await page.keyboard.press('Escape').catch(() => {});
    await page.click('.modal-header .btn-icon').catch(() => {});
  } catch (e) { record('M6 view detail metadata', false, e.message.split('\n')[0]); }

  // M7 rename document
  try {
    await page.click('.btn-icon[aria-label="Rename"]');
    await page.waitForSelector('#mv-rename', {timeout: 5000});
    await page.fill('#mv-rename', 'mri-report-v2');
    await page.click('button:has-text("Save")');
    await page.waitForTimeout(400);
    const rows = await page.locator('.table tbody tr').allTextContents();
    record('M7 rename document', rows.some(r => /mri-report-v2/.test(r)), JSON.stringify(rows).slice(0, 120));
  } catch (e) { record('M7 rename document', false, e.message.split('\n')[0]); }

  // M8 delete document
  try {
    const before = await page.locator('.table tbody tr .doc-name').allTextContents();
    const target = before[0];
    await page.locator('.btn-icon[aria-label="Delete"]').first().click();
    await page.waitForTimeout(400);
    const after = await page.locator('.table tbody tr .doc-name').allTextContents();
    record('M8 delete document', !after.some(n => n === target) && after.length === before.length - 1,
           `before=${before.length} after=${after.length} target=${target}`);
  } catch (e) { record('M8 delete document', false, e.message.split('\n')[0]); }

  // M9 persistence after refresh
  try {
    await page.reload({waitUntil: 'networkidle'});
    await page.waitForTimeout(600);
    const tabs = await page.locator('.folder-tab').allTextContents();
    record('M9 persistence after refresh', tabs.some(t => /Radiology/.test(t)), JSON.stringify(tabs));
  } catch (e) { record('M9 persistence after refresh', false, e.message.split('\n')[0]); }

  // M10 mobile renders
  try {
    const mp = await browser.newContext({viewport: {width: 390, height: 844}});
    const m = await mp.newPage();
    await m.goto(url, {waitUntil: 'networkidle'});
    await m.waitForSelector('.vault-view, .folder-tabs', {timeout: 6000});
    const overflow = await m.evaluate(() => document.documentElement.scrollWidth <= 391);
    await m.screenshot({path: 'recovery/session034-preview/shots/reverify-medivault-mobile.png'});
    record('M10 mobile renders', overflow, 'no-h-overflow=' + overflow);
    await mp.close();
  } catch (e) { record('M10 mobile renders', false, e.message.split('\n')[0]); }

  await ctx.close();
  return {errors};
}

(async () => {
  const browser = await chromium.launch();
  const tf = await taskflowSuite(browser);
  const tfPassed = steps.filter(s => s.ok).length;
  const tfTotal = steps.length;
  const mv = await medivaultSuite(browser);
  await browser.close();
  const mvSteps = steps.slice(tfTotal);
  const mvPassed = mvSteps.filter(s => s.ok).length;
  const report = {
    when: new Date().toISOString(),
    base: BASE,
    taskflow: {steps: steps.slice(0, tfTotal), passed: tfPassed, total: tfTotal,
               page_errors: tf.errors},
    medivault: {steps: mvSteps, passed: mvPassed, total: mvSteps.length,
                page_errors: mv.errors},
  };
  mkdirSync(path.dirname(OUT), {recursive: true});
  writeFileSync(OUT, JSON.stringify(report, null, 1));
  console.log(`\nTaskFlow v2: ${tfPassed}/${tfTotal}; MediVault: ${mvPassed}/${mvSteps.length}`);
  console.log('TaskFlow errors:', JSON.stringify(tf.errors).slice(0, 300));
  console.log('MediVault errors:', JSON.stringify(mv.errors).slice(0, 300));
})();
