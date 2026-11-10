// Trusted Session-040 fullstack-integration evaluator runner. Executes ONLY
// inside the restricted execution tier. Boots the trusted Prisma+SQLite
// fixture in /work, installs an in-process fetch shim that routes the frozen
// route path to the TRUSTED reference route (real database behind it),
// transpiles the candidate TSX with esbuild into /work, renders it with
// @testing-library/react and replays the frozen oracle flow: valid create
// (201 -> visible item + incremented total -> persisted through GET ->
// survives remount), 400/404/409 failures (error visible, no phantom rows,
// form preserved), and a final no-phantom refresh. Emits exactly one
// S040-RESULT verdict; every failure is fail-closed.
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';
import { copyFile, mkdir, writeFile, readFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);
const MARK = 'S040-RESULT ';
const stdoutWrite = process.stdout.write.bind(process.stdout);
const emit = (record) => stdoutWrite(MARK + JSON.stringify(record) + '\n');

const HARNESS = process.env.S040_HARNESS ?? '/harness';
const CANDIDATE = process.env.S040_CANDIDATE ?? '/candidate/output.tsx';
const WORK = process.env.S040_WORK ?? '/work';
const DEPS = '/eval-deps/node_modules';
const WATCHDOG_MS = Number(process.env.S040_WATCHDOG_MS ?? 170_000);

let checks = [];
let done = false;
const finish = (pass, status) => {
  if (done) { process.exit(1); }
  done = true;
  emit({ pass, checks, status });
  process.exit(0); // exit code is the anti-spoof trust anchor; verdict carries pass/fail
};
const watchdog = setTimeout(() => finish(false, 'watchdog-timeout'), WATCHDOG_MS);
watchdog.unref?.();
const fail = (name, detail) => { checks.push({ name, passed: false, detail: String(detail).slice(0, 200) }); };
const ok = (name) => { checks.push({ name, passed: true }); };

async function prismaStep(args) {
  try {
    await run('prisma', args, { cwd: WORK, env: { ...process.env, PRISMA_HIDE_UPDATE_MESSAGE: '1' } });
  } catch (error) {
    const detail = `rc=${error.code} | out: ${String(error.stdout || '').slice(0, 150)} | err: ${String(error.stderr || '').slice(-450)}`;
    const wrapped = new Error(detail);
    throw wrapped;
  }
}

async function main() {
  const spec = JSON.parse(await readFile(`${HARNESS}/task.json`, 'utf8'));
  const source = await readFile(CANDIDATE, 'utf8');

  // 1. Boot the trusted Prisma+SQLite fixture in the writable workspace.
  await mkdir(`${WORK}/lib`, { recursive: true });
  for (const [src, dst] of [
    ['schema.prisma', 'schema.prisma'], ['db.ts', 'lib/db.ts'],
    ['fixture.mjs', 'fixture.mjs'], ['seed.mjs', 'seed.mjs'], ['route.mjs', 'route.mjs'],
  ]) { await copyFile(`${HARNESS}/${src}`, `${WORK}/${dst}`); }
  await prismaStep(['db', 'push', '--schema', `${WORK}/schema.prisma`, '--skip-generate', '--accept-data-loss']);
  await prismaStep(['generate', '--schema', `${WORK}/schema.prisma`]);
  await run('node', [`${WORK}/seed.mjs`], { cwd: WORK });

  // 2. jsdom globals BEFORE react-dom.
  const { createRequire } = await import('node:module');
  const req = createRequire(`${DEPS}/`);
  const { JSDOM } = req('jsdom');
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true });
  const props = ['document', 'HTMLElement', 'Element', 'Node', 'Event', 'CustomEvent',
    'KeyboardEvent', 'MouseEvent', 'getComputedStyle', 'requestAnimationFrame',
    'cancelAnimationFrame', 'MutationObserver', 'DOMParser', 'HTMLInputElement',
    'HTMLSelectElement', 'HTMLTextAreaElement', 'HTMLButtonElement', 'HTMLFormElement'];
  for (const p of props) {
    const v = dom.window[p];
    if (v === undefined) { continue; }
    try { globalThis[p] = v; } catch { /* read-only Node global */ }
  }
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);

  // 3. Redirect bare specifiers to the pinned toolchain, import the trusted
  //    reference route, then install the in-process fetch shim.
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (!specifier.startsWith('.') && !specifier.startsWith('/') && !specifier.startsWith('node:')) {
        return nextResolve(specifier, { ...context, parentURL: pathToFileURL(`${DEPS}/x.js`).href });
      }
      return nextResolve(specifier, context);
    },
  });
  const routeModule = await import(pathToFileURL(`${WORK}/route.mjs`).href);
  const fetchLog = [];
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || String(input);
    const method = String((init && init.method) || (typeof input === 'object' && input && input.method) || 'GET').toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0];
    fetchLog.push({ method, path, status: null });
    const entry = fetchLog[fetchLog.length - 1];
    if (path !== spec.route_path || !routeModule[method]) {
      entry.status = 404;
      return new Response(JSON.stringify({ error: 'not-found', message: `No route for ${method} ${path}` }), { status: 404 });
    }
    const request = new Request(`http://localhost${spec.route_path}`, {
      method,
      body: method === 'GET' || method === 'HEAD' ? undefined : (init && init.body),
      headers: { 'content-type': 'application/json', ...(init && init.headers) },
    });
    const response = await routeModule[method](request);
    entry.status = response.status;
    return response;
  };

  // 4. Transpile + import the candidate.
  const esbuild = req('esbuild');
  let compiled;
  try {
    compiled = await esbuild.transform(source, { loader: 'tsx', jsx: 'automatic', format: 'esm', target: 'node20' });
  } catch (error) {
    fail('candidate-transpiles', error.errors ? error.errors[0] && error.errors[0].text : String(error));
    return finish(false, 'candidate-transpile-failed');
  }
  await writeFile(`${WORK}/component.mjs`, compiled.code, 'utf8');
  let component;
  try {
    const mod = await import(pathToFileURL(`${WORK}/component.mjs`).href);
    component = mod.default;
  } catch (error) {
    fail('candidate-imports', error instanceof Error ? error.message : String(error));
    return finish(false, 'candidate-import-failed');
  }
  if (typeof component !== 'function' && (component == null || typeof component !== 'object')) {
    fail('default-export-component', 'default export must be a React component');
    return finish(false, 'invalid-export');
  }

  const { render, cleanup, fireEvent, act } = req('@testing-library/react');
  const React = req('react');
  const dbModule = await import(pathToFileURL(`${WORK}/lib/db.ts`).href);
  const seedModule = await import(pathToFileURL(`${WORK}/fixture.mjs`).href);

  const flush = async () => { await act(async () => {}); };
  const settle = async (ms = 40) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)); }); };
  const mount = async () => {
    cleanup();
    render(React.createElement(component), { container: document.getElementById('root') });
    await settle(60);
  };
  const accessibleName = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) {
      const escaped = el.id.replace(/(["\\])/g, '\\$1');
      const label = document.querySelector(`label[for="${escaped}"]`);
      if (label && label.textContent.trim()) return label.textContent;
    }
    if (el.closest('label') && el.closest('label').textContent.trim()) return el.closest('label').textContent;
    if (el.tagName === 'BUTTON' || el.tagName === 'OPTION') return el.textContent || '';
    return el.getAttribute('placeholder') || '';
  };
  const labelField = spec.fields.label, amountField = spec.fields.amount, fkField = spec.entities.foreign_key;
  const findInput = (re) => [...document.querySelectorAll('input')].find((i) => {
    const hay = `${accessibleName(i)} ${i.id || ''} ${i.getAttribute('name') || ''}`.toLowerCase();
    return re.test(hay);
  });
  const titleInput = () => findInput(new RegExp(`${labelField}|title|name|label`, 'i'));
  const amountInput = () => findInput(new RegExp(`${amountField}|amount|minute|min`, 'i')) ||
    [...document.querySelectorAll('input[type=number]')][0];
  const fkSelect = () => [...document.querySelectorAll('select')].find((s) =>
    new RegExp(`${fkField}|${spec.entities.parent_client}|parent|relation|link`, 'i')
      .test(`${accessibleName(s)} ${s.id || ''} ${s.getAttribute('name') || ''}`.toLowerCase()));
  const submitTrigger = () => {
    const form = document.querySelector('form');
    const btn = [...document.querySelectorAll('button')].find((b) => /add|create|save|submit/i.test(b.textContent || ''));
    return { form, btn };
  };
  const readTotal = () => {
    const leaves = [...document.querySelectorAll('body *')].filter((el) => el.children.length === 0);
    for (const el of leaves) {
      const text = el.textContent || '';
      if (/total|count/i.test(text)) {
        const m = text.match(/\d+/);
        if (m) return Number(m[0]);
      }
    }
    return null;
  };
  const errorRe = () => new RegExp(spec.conventions.error_text_re, 'i');
  const errorVisible = (beforeText) => {
    const alert = document.querySelector('[role="alert"]');
    if (alert && (alert.textContent || '').trim()) return true;
    const after = document.body.textContent || '';
    return after.split(/[\n.!?]+/).map((s) => s.trim()).some((s) => s.length > 3 && errorRe().test(s) && !beforeText.includes(s));
  };
  const doSubmit = async () => {
    const { form, btn } = submitTrigger();
    if (form) { fireEvent.submit(form); }
    else if (btn) { fireEvent.click(btn); }
    else { throw new Error('no form or submit button'); }
    await settle(80);
  };
  const fillForm = async (title, amount, fk) => {
    const t = titleInput(), a = amountInput(), f = fkSelect();
    if (!t || !a) throw new Error(`form inputs missing (title=${!!t} amount=${!!a})`);
    fireEvent.change(t, { target: { value: title } });
    if (a) fireEvent.change(a, { target: { value: String(amount) } });
    if (f) {
      if (fk === 'missing' && ![...f.options].some((o) => o.value === 'missing')) {
        fireEvent.change(f, { target: { innerHTML: f.innerHTML + '<option value="missing">missing</option>' } });
        const added = f.lastElementChild;
        if (added) added.value = 'missing';
      }
      fireEvent.change(f, { target: { value: fk } });
    }
    await flush();
  };
  const lastStatus = (method) => {
    for (let i = fetchLog.length - 1; i >= 0; i--) {
      if (fetchLog[i].method === method) return fetchLog[i].status;
    }
    return null;
  };
  const getRouteJson = async () => {
    const res = await globalThis.fetch(spec.route_path, { method: 'GET' });
    return { status: res.status, body: await res.json() };
  };
  const reseed = async () => { await seedModule.seedFixture(dbModule.db); };

  const newTitle = 'New item';
  const fixtureTotal = spec.fixture.children.length;

  // ---------- positive flow ----------
  await reseed();
  await mount();
  let totalBefore = readTotal();
  let beforeText = document.body.textContent || '';
  await fillForm(newTitle, spec.fields.min_inclusive, 'parent-a');
  await doSubmit();
  const status201 = lastStatus('POST');
  const caseByName = Object.fromEntries(spec.cases.map((c) => [c.name, c]));
  if (caseByName['create-201']) {
    checks.push({ name: 'create-201', passed: status201 === 201, detail: `POST status=${status201}` });
  }
  if (caseByName['visible-immediately']) {
    const body = document.body.textContent || '';
    const totalAfter = readTotal();
    const visible = body.includes(newTitle);
    const incremented = totalAfter !== null && totalBefore !== null ? totalAfter === totalBefore + 1 : totalAfter === fixtureTotal + 1;
    checks.push({ name: 'visible-immediately', passed: visible && incremented, detail: `visible=${visible} total=${totalAfter} before=${totalBefore}` });
  }
  if (caseByName['get-persisted']) {
    const { status, body } = await getRouteJson();
    const present = JSON.stringify(body).includes(newTitle);
    checks.push({ name: 'get-persisted', passed: status === 200 && present, detail: `GET status=${status} present=${present}` });
  }
  if (caseByName['refresh-survives']) {
    await mount();
    const visibleAfterRemount = (document.body.textContent || '').includes(newTitle);
    const { body } = await getRouteJson();
    checks.push({ name: 'refresh-survives', passed: visibleAfterRemount && JSON.stringify(body).includes(newTitle), detail: `remountVisible=${visibleAfterRemount}` });
  }

  // ---------- negative flows (fresh seed) ----------
  if (caseByName['post-400']) {
    await reseed(); await mount();
    beforeText = document.body.textContent || '';
    totalBefore = readTotal();
    await fillForm('   ', spec.fields.min_inclusive, 'parent-a');
    await doSubmit();
    const s = lastStatus('POST');
    const err = errorVisible(beforeText);
    const noPhantom = readTotal() === totalBefore;
    checks.push({ name: 'post-400', passed: s === 400 && err && noPhantom, detail: `status=${s} error=${err} noPhantom=${noPhantom}` });
  }
  if (caseByName['post-404']) {
    await reseed(); await mount();
    beforeText = document.body.textContent || '';
    totalBefore = readTotal();
    const hasFk = !!fkSelect();
    if (!hasFk) {
      fail('post-404', 'no relation select in form (404 case requires the relation field)');
    } else {
      await fillForm('Valid', spec.fields.min_inclusive, 'missing');
      await doSubmit();
      const s = lastStatus('POST');
      const err = errorVisible(beforeText);
      const noPhantom = !(document.body.textContent || '').includes('Valid') && readTotal() === totalBefore;
      checks.push({ name: 'post-404', passed: s === 404 && err && noPhantom, detail: `status=${s} error=${err} noPhantom=${noPhantom}` });
    }
  }
  if (caseByName['post-409']) {
    await reseed(); await mount();
    beforeText = document.body.textContent || '';
    totalBefore = readTotal();
    const dup = spec.fixture.children[0][labelField];
    await fillForm(dup, spec.fields.min_inclusive, 'parent-a');
    await doSubmit();
    const s = lastStatus('POST');
    const err = errorVisible(beforeText);
    const noPhantom = readTotal() === totalBefore;
    checks.push({ name: 'post-409', passed: s === 409 && err && noPhantom, detail: `status=${s} error=${err} noPhantom=${noPhantom}` });
  }
  if (caseByName['refresh-after-error']) {
    await reseed(); await mount();
    const { body } = await getRouteJson();
    const envelope = body && body[spec.envelope_key];
    const totalOk = envelope ? envelope.length === fixtureTotal : false;
    checks.push({ name: 'refresh-after-error', passed: totalOk, detail: `rows=${envelope ? envelope.length : 'n/a'} expected=${fixtureTotal}` });
  }

  await dbModule.db.$disconnect().catch(() => {});
  const pass = checks.length > 0 && checks.every((c) => c.passed);
  return finish(pass, pass ? 'all-cases-passed' : 'case-failures');
}

main().catch((error) => { fail('runner-error', error instanceof Error ? error.stack : String(error)); finish(false, 'runner-error'); });
