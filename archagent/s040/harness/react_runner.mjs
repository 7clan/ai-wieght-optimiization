// Trusted Session-040 react-interaction evaluator runner. Executes ONLY
// inside the restricted execution tier (Docker in approved CI, or the
// disclosed unshare user+network namespace locally). Stages a jsdom
// environment, transpiles the candidate TSX with esbuild into /work (never
// modifying the candidate file), redirects all bare module specifiers to the
// pinned /eval-deps toolchain, renders the component with the frozen fixture
// rows and replays the frozen oracle cases (render, search, status filter,
// combined, empty state, clear, keyboard accessibility, 320px width audit).
// Emits exactly one S040-RESULT verdict line; every failure is fail-closed.
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';
import { writeFile, readFile } from 'node:fs/promises';

const MARK = 'S040-RESULT ';
// Bind the real stdout write before candidate code can monkey-patch it.
const stdoutWrite = process.stdout.write.bind(process.stdout);
const emit = (record) => stdoutWrite(MARK + JSON.stringify(record) + '\n');

const HARNESS = process.env.S040_HARNESS ?? '/harness';
const CANDIDATE = process.env.S040_CANDIDATE ?? '/candidate/output.tsx';
const WORK = process.env.S040_WORK ?? '/work';
const DEPS = '/eval-deps/node_modules';
const WATCHDOG_MS = Number(process.env.S040_WATCHDOG_MS ?? 120_000);

let checks = [];
let done = false;
const finish = (pass, status) => {
  if (done) { process.exit(1); }
  done = true;
  emit({ pass, checks, status });
  // Exit 0 whenever a verdict was emitted (pass OR fail): the controller
  // treats a nonzero exit as an infrastructure failure and discards stdout,
  // so the exit code is the anti-spoofing trust anchor. Only crashes before
  // a verdict yield a nonzero exit.
  process.exit(0);
};
const watchdog = setTimeout(() => finish(false, 'watchdog-timeout'), WATCHDOG_MS);
watchdog.unref?.();

const fail = (name, detail) => { checks.push({ name, passed: false, detail: String(detail).slice(0, 200) }); };

async function main() {
  const spec = JSON.parse(await readFile(`${HARNESS}/task.json`, 'utf8'));
  const conventions = spec.conventions;
  const fixture = spec.fixture;
  const titles = spec.titles;
  const source = await readFile(CANDIDATE, 'utf8');

  // 1. jsdom globals BEFORE react-dom is loaded.
  const { createRequire } = await import('node:module');
  const req = createRequire(`${DEPS}/`);
  const { JSDOM } = req('jsdom');
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>',
    { url: 'http://localhost/', pretendToBeVisual: true });
  const props = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node',
    'Event', 'CustomEvent', 'KeyboardEvent', 'MouseEvent', 'getComputedStyle',
    'requestAnimationFrame', 'cancelAnimationFrame', 'MutationObserver', 'SVGElement',
    'DOMParser', 'HTMLInputElement', 'HTMLSelectElement', 'HTMLTextAreaElement',
    'HTMLButtonElement', 'HTMLFormElement'];
  for (const p of props) {
    const v = dom.window[p];
    if (v === undefined) { continue; }
    try { globalThis[p] = v; } catch { /* Node-24 provides some read-only globals (e.g. navigator); jsdom's document/window below are the ones React needs */ }
  }
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.addEventListener = dom.window.addEventListener.bind(dom.window);
  globalThis.removeEventListener = dom.window.removeEventListener.bind(dom.window);

  // 2. Transpile the candidate TSX into the writable workspace.
  const esbuild = req('esbuild');
  let compiled;
  try {
    compiled = await esbuild.transform(source, {
      loader: 'tsx', jsx: 'automatic', format: 'esm', target: 'node20', sourcemap: false,
    });
  } catch (error) {
    fail('candidate-transpiles', error.errors ? error.errors[0]?.text : String(error));
    return finish(false, 'candidate-transpile-failed');
  }
  await writeFile(`${WORK}/component.mjs`, compiled.code, 'utf8');

  // 3. Redirect every bare specifier to the pinned toolchain.
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (!specifier.startsWith('.') && !specifier.startsWith('/') && !specifier.startsWith('node:')) {
        return nextResolve(specifier, { ...context, parentURL: pathToFileURL(`${DEPS}/x.js`).href });
      }
      return nextResolve(specifier, context);
    },
  });

  // 4. Import the candidate module and find the default export.
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

  const { render, cleanup, fireEvent } = req('@testing-library/react');
  const React = req('react');

  const countTitles = () => {
    const text = document.body.textContent || '';
    return titles.filter((t) => text.includes(t)).length;
  };
  const textMatches = (re) => re.test(document.body.textContent || '');
  const accessibleName = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const labels = labelledby.split(/\s+/).map((id) => document.getElementById(id))
        .filter(Boolean).map((n) => n.textContent).join(' ');
      if (labels.trim()) return labels;
    }
    if (el.id) {
      const escaped = el.id.replace(/(["\\])/g, '\\$1');
      const label = document.querySelector(`label[for="${escaped}"]`);
      if (label && label.textContent.trim()) return label.textContent;
    }
    if (el.closest('label') && el.closest('label').textContent.trim()) return el.closest('label').textContent;
    if (el.tagName === 'BUTTON') return el.textContent || '';
    return el.getAttribute('placeholder') || '';
  };
  const findSearchInput = () => {
    const inputs = [...document.querySelectorAll('input')];
    return inputs.find((i) => ['text', 'search', ''].includes((i.getAttribute('type') || '').toLowerCase())) || null;
  };
  const findStatusSelect = () => {
    const selects = [...document.querySelectorAll('select')];
    return selects.find((s) => new RegExp(conventions.status_name_re, 'i').test(accessibleName(s))) || null;
  };
  const findClearButton = () => {
    const re = new RegExp(conventions.clear_button_re, 'i');
    return [...document.querySelectorAll('button')].find((b) => re.test(b.textContent || '')) || null;
  };
  const findEmptyState = () => {
    if (document.querySelector('[data-testid="empty-state"]')) return true;
    return textMatches(new RegExp(conventions.empty_state_re, 'i'));
  };
  const mount = () => {
    cleanup();
    render(React.createElement(component, { data: fixture.children }), { container: document.getElementById('root') });
  };
  const flush = async () => { const { act } = req('@testing-library/react'); await act(async () => {}); };

  const runCase = async (c) => {
    const name = c.name;
    try {
      mount();
      await flush();
      if (c.event === 'initial-render') {
        checks.push({ name, passed: countTitles() === c.expected_count, detail: `count=${countTitles()}` });
      } else if (c.event === 'type-search') {
        const input = findSearchInput();
        if (!input) return fail(name, 'no text input found');
        fireEvent.change(input, { target: { value: c.query } });
        await flush();
        if (c.expected === 'explicit-empty-state') {
          checks.push({ name, passed: countTitles() === 0 && findEmptyState(), detail: `count=${countTitles()} emptyState=${findEmptyState()}` });
        } else {
          checks.push({ name, passed: countTitles() === c.expected_count, detail: `count=${countTitles()} query=${c.query}` });
        }
      } else if (c.event === 'choose-status') {
        const select = findStatusSelect();
        if (!select) return fail(name, 'no labeled status select found');
        fireEvent.change(select, { target: { value: c.status } });
        await flush();
        checks.push({ name, passed: countTitles() === c.expected_count, detail: `count=${countTitles()} status=${c.status}` });
      } else if (c.event === 'search-and-status') {
        const input = findSearchInput();
        const select = findStatusSelect();
        if (!input || !select) return fail(name, 'missing input/select');
        fireEvent.change(input, { target: { value: c.query } });
        fireEvent.change(select, { target: { value: c.status } });
        await flush();
        checks.push({ name, passed: countTitles() === c.expected_count, detail: `count=${countTitles()}` });
      } else if (c.event === 'clear-filters') {
        const input = findSearchInput();
        const button = findClearButton();
        if (!input || !button) return fail(name, 'missing search input or clear button');
        fireEvent.change(input, { target: { value: titles[0].slice(0, 2).toLowerCase() } });
        await flush();
        fireEvent.click(button);
        await flush();
        checks.push({ name, passed: countTitles() === c.expected_count, detail: `count=${countTitles()} after clear` });
      } else if (c.event === 'keyboard-only-interaction') {
        const problems = [];
        const interactive = [...document.querySelectorAll('input, select, button, textarea, [tabindex]')];
        if (interactive.length < 3) problems.push('fewer than 3 interactive elements');
        for (const el of interactive) {
          const tag = el.tagName;
          if (!['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA'].includes(tag)
              && el.getAttribute('tabindex') !== '0') { problems.push(`non-native focusable ${tag}`); continue; }
          if (tag === 'INPUT' && el.getAttribute('type') === 'hidden') continue;
          if (!accessibleName(el).trim()) problems.push(`unlabeled <${tag.toLowerCase()}>`);
        }
        const input = findSearchInput();
        if (input) { try { input.focus(); if (document.activeElement !== input) problems.push('search input not focusable'); } catch { problems.push('focus threw'); } }
        checks.push({ name, passed: problems.length === 0, detail: problems.slice(0, 3).join('; ') || 'ok' });
      } else if (c.event === 'viewport-320') {
        const problems = [];
        try { Object.defineProperty(dom.window, 'innerWidth', { configurable: true, value: 320 }); } catch { /* jsdom may refuse */ }
        const widthRe = /(?:^|[^-\w])(?:min-)?width\s*:\s*(\d{3,})px/g;
        for (const style of [...document.querySelectorAll('style')]) {
          const text = style.textContent || '';
          let m;
          while ((m = widthRe.exec(text))) {
            if (Number(m[1]) > 320) problems.push(`stylesheet width ${m[1]}px`);
          }
        }
        for (const el of [...document.querySelectorAll('*')]) {
          const inline = el.getAttribute('style') || '';
          const mm = inline.match(/(?:min-)?width\s*:\s*(\d{3,})px/);
          if (mm && Number(mm[1]) > 320) problems.push(`<${el.tagName.toLowerCase()}> width ${mm[1]}px`);
        }
        checks.push({ name, passed: problems.length === 0, detail: problems.slice(0, 3).join('; ') || 'ok (static audit; jsdom cannot compute layout)' });
      } else {
        fail(name, `unknown event ${c.event}`);
      }
    } catch (error) {
      fail(name, error instanceof Error ? error.message : String(error));
    }
  };

  for (const c of spec.cases) { await runCase(c); }
  const pass = checks.length > 0 && checks.every((c) => c.passed);
  return finish(pass, pass ? 'all-cases-passed' : 'case-failures');
}

main().catch((error) => { fail('runner-error', error instanceof Error ? error.stack : String(error)); finish(false, 'runner-error'); });
