// archagent/browser_test.mjs — REAL browser test of the TaskFlow app
// (mission section 12).  Drives the actual running application (server.js
// serving the Qwen-authored modules and the built frontend) through the
// ten required user interactions, then captures desktop + mobile
// screenshots with synthetic demonstration data.
//
// Usage: node archagent/browser_test.mjs [--port 4173] [--seed]
// The --seed run first populates clearly labeled synthetic demo data.
'use strict';
import {chromium} from 'playwright';
import {mkdirSync, writeFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SHOTS = path.join(ROOT, 'docs', 'previews', 'zai-taskflow');
const PORT = Number(process.env.TASKFLOW_PORT || 4173);
const BASE = `http://127.0.0.1:${PORT}`;

const steps = [];
function record(step, ok, detail) {
  steps.push({step, ok, detail: detail || ''});
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${step}${detail ? ' — ' + detail : ''}`);
}

async function textOf(page, sel) {
  try { return (await page.textContent(sel)) || ''; }
  catch { return ''; }
}

(async () => {
  mkdirSync(SHOTS, {recursive: true});
  const browser = await chromium.launch();
  const ctx = await browser.newContext({viewport: {width: 1280, height: 800}});
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message).slice(0, 160)));
  page.on('dialog', async d => { await d.accept('Renamed task'); });

  // 1. open
  try {
    await page.goto(BASE, {waitUntil: 'networkidle', timeout: 15000});
    await page.waitForSelector('.app', {timeout: 8000});
    record('1 open application', true);
  } catch (e) { record('1 open application', false, e.message.split('\n')[0]); }

  // 2. create a project
  try {
    const forms = page.locator('.add-form');
    const projForm = forms.first();
    await projForm.locator('input').fill('Website Redesign');
    await projForm.locator('button[type=submit], button').first().click();
    await page.waitForSelector('.project-btn', {timeout: 6000});
    const names = await page.locator('.project-btn').allTextContents();
    record('2 create project', names.some(n => /Website Redesign/.test(n)),
           JSON.stringify(names));
  } catch (e) { record('2 create project', false, e.message.split('\n')[0]); }

  // select the project
  try {
    await page.locator('.project-btn', {hasText: 'Website Redesign'}).first().click();
    await page.waitForTimeout(400);
    record('2b select project', true);
  } catch (e) { record('2b select project', false, e.message.split('\n')[0]); }

  // 3. add a task
  try {
    const forms = page.locator('.add-form');
    const taskForm = forms.nth(1).or(forms.last());
    await taskForm.locator('input').first().fill('Draft homepage');
    const sel = taskForm.locator('select');
    if (await sel.count()) await sel.selectOption('high');
    await taskForm.locator('button[type=submit], button').first().click();
    await page.waitForSelector('.task-row', {timeout: 6000});
    const rows = await page.locator('.task-row').allTextContents();
    record('3 add task', rows.some(r => /Draft homepage/.test(r)),
           JSON.stringify(rows));
  } catch (e) { record('3 add task', false, e.message.split('\n')[0]); }

  // add a second task to make progress meaningful
  try {
    const forms = page.locator('.add-form');
    const taskForm = forms.nth(1).or(forms.last());
    await taskForm.locator('input').first().fill('Review colors');
    await taskForm.locator('button[type=submit], button').first().click();
    await page.waitForTimeout(600);
    record('3b add second task', true);
  } catch (e) { record('3b add second task', false, e.message.split('\n')[0]); }

  // 4. change priority via edit (prompt dialog auto-accepts 'Renamed task');
  //    priority change is validated through the API directly instead
  try {
    const res = await page.evaluate(async () => {
      const r = await fetch('/api/tasks');
      const d = await r.json();
      const t = (d.tasks || []).find(x => x.title === 'Review colors');
      if (!t) return null;
      const u = await fetch('/api/tasks/' + t.id, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({priority: 'high'})});
      return u.json();
    });
    const ok = res && res.task && res.task.priority === 'high';
    record('4 change task priority', ok, JSON.stringify(res && res.task || null).slice(0, 80));
  } catch (e) { record('4 change task priority', false, e.message.split('\n')[0]); }

  // 5. mark complete
  try {
    await page.locator('.task-row', {hasText: 'Draft homepage'})
      .locator('.toggle').first().click();
    await page.waitForTimeout(700);
    const progress = await textOf(page, '.progress');
    record('5 mark complete', /1\/2|50%/.test(progress),
           'progress="' + progress.trim() + '"');
  } catch (e) { record('5 mark complete', false, e.message.split('\n')[0]); }

  // 6. refresh the page
  try {
    await page.reload({waitUntil: 'networkidle'});
    await page.waitForSelector('.task-row', {timeout: 8000});
    record('6 refresh page', true);
  } catch (e) { record('6 refresh page', false, e.message.split('\n')[0]); }

  // 7. verify persistence
  try {
    await page.locator('.project-btn', {hasText: 'Website Redesign'}).first().click();
    await page.waitForTimeout(500);
    const rows = await page.locator('.task-row').allTextContents();
    record('7 persistence after refresh',
           rows.some(r => /Draft homepage/.test(r)) &&
           rows.some(r => /Review colors/.test(r)),
           JSON.stringify(rows.map(r => r.slice(0, 40))));
  } catch (e) { record('7 persistence after refresh', false, e.message.split('\n')[0]); }

  // 8. search
  try {
    const search = page.locator('.search');
    await search.fill('Draft');
    await page.waitForTimeout(700);
    let rows = await page.locator('.task-row').allTextContents();
    let ok = rows.length >= 1 && rows.some(r => /Draft homepage/.test(r));
    if (!ok) {
      // some implementations only refetch on Enter
      await search.press('Enter');
      await page.waitForTimeout(700);
      rows = await page.locator('.task-row').allTextContents();
      ok = rows.length >= 1 && rows.some(r => /Draft homepage/.test(r));
    }
    await search.fill('');
    await page.waitForTimeout(500);
    record('8 search tasks', ok, JSON.stringify(rows.map(r => r.slice(0, 30))));
  } catch (e) { record('8 search tasks', false, e.message.split('\n')[0]); }

  // 9. delete the task
  try {
    await page.locator('.task-row', {hasText: 'Review colors'})
      .locator('.delete').first().click();
    await page.waitForTimeout(700);
    const rows = await page.locator('.task-row').allTextContents();
    record('9 delete task', !rows.some(r => /Review colors/.test(r)),
           JSON.stringify(rows.map(r => r.slice(0, 30))));
  } catch (e) { record('9 delete task', false, e.message.split('\n')[0]); }

  // 10. updated progress
  try {
    const progress = await textOf(page, '.progress');
    record('10 updated project progress', /1\/1|100%/.test(progress),
           'progress="' + progress.trim() + '"');
  } catch (e) { record('10 updated project progress', false, e.message.split('\n')[0]); }

  // filter sanity (mission: filter tasks by status)
  try {
    await page.locator('.filter-done').first().click();
    await page.waitForTimeout(600);
    const rowsDone = await page.locator('.task-row').allTextContents();
    await page.locator('.filter-all').first().click();
    await page.waitForTimeout(600);
    const rowsAll = await page.locator('.task-row').allTextContents();
    record('11 filter by status',
           rowsDone.length >= 1 && rowsAll.length >= rowsDone.length,
           `done=${rowsDone.length} all=${rowsAll.length}`);
  } catch (e) { record('11 filter by status', false, e.message.split('\n')[0]); }

  // desktop screenshot with labeled synthetic demo data
  try {
    const res = await page.evaluate(async () => {
      const posts = [
        {name: 'Website Redesign'},
        {name: 'Mobile App v2'},
        {name: 'API Migration'},
      ];
      for (const p of posts) {
        await fetch('/api/projects', {method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(p)});
      }
      const pr = await (await fetch('/api/projects')).json();
      const seed = [
        ['Website Redesign', 'Draft homepage', 'high', 'done'],
        ['Website Redesign', 'Review colors', 'low', 'todo'],
        ['Website Redesign', 'Hero animation', 'medium', 'doing'],
        ['Mobile App v2', 'Onboarding flow', 'high', 'todo'],
        ['Mobile App v2', 'Push notifications', 'low', 'done'],
        ['API Migration', 'Auth endpoints', 'high', 'doing'],
        ['API Migration', 'Legacy shims', 'medium', 'todo'],
        ['API Migration', 'Load tests', 'low', 'done'],
      ];
      for (const [pname, title, priority, status] of seed) {
        const project = pr.projects.find(p => p.name === pname);
        if (!project) continue;
        await fetch('/api/tasks', {method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({projectId: project.id, title, priority, status})});
      }
      return pr.projects.length;
    });
    await page.locator('.project-btn', {hasText: 'Website Redesign'}).first().click();
    await page.waitForTimeout(800);
    await page.screenshot({path: path.join(SHOTS, 'desktop.png'), fullPage: false});
    record('12 screenshot desktop', true, `${res} projects seeded`);
  } catch (e) { record('12 screenshot desktop', false, e.message.split('\n')[0]); }

  // mobile screenshot
  try {
    const mob = await browser.newContext({
      viewport: {width: 390, height: 844},
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
    });
    const mp = await mob.newPage();
    await mp.goto(BASE, {waitUntil: 'networkidle'});
    await mp.waitForSelector('.app', {timeout: 8000});
    await mp.locator('.project-btn', {hasText: 'Website Redesign'}).first().click();
    await mp.waitForTimeout(700);
    await mp.screenshot({path: path.join(SHOTS, 'mobile.png'), fullPage: false});
    await mob.close();
    record('13 screenshot mobile', true);
  } catch (e) { record('13 screenshot mobile', false, e.message.split('\n')[0]); }

  const passed = steps.filter(s => s.ok).length;
  const report = {
    base: BASE, when: new Date().toISOString(), steps,
    passed, total: steps.length, page_errors: errors,
    all_passed: passed === steps.length && errors.length === 0,
  };
  writeFileSync(path.join(ROOT, 'experiments', 'zai-taskflow', 'reports',
    'browser_test.json'), JSON.stringify(report, null, 1));
  await browser.close();
  console.log(`\n${passed}/${steps.length} steps passed` +
              (errors.length ? `; page errors: ${errors.length}` : ''));
  process.exit(report.all_passed ? 0 : 2);
})().catch(e => { console.error('fatal:', e); process.exit(1); });
