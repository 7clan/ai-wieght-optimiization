// Trusted behavioral evaluator. Generated HTML/JS runs only inside the
// network-disabled, read-only, nonroot, resource-capped Docker container.
const fs = require('node:fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync('/candidate/index.html', 'utf8');
const persisted = new Map();
const assertions = [];
const errors = [];

function check(name, ok, reason = '') {
  assertions.push({ name, passed: Boolean(ok), reason: ok ? '' : reason });
}
function createPage() {
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push(String(e.message).slice(0, 250)));
  const dom = new JSDOM(html, {
    url: 'https://offline.example.invalid/',
    runScripts: 'dangerously',
    virtualConsole: vc,
    beforeParse(window) {
      const localStorage = {
        getItem: key => persisted.has(String(key)) ? persisted.get(String(key)) : null,
        setItem: (key, value) => persisted.set(String(key), String(value)),
        removeItem: key => persisted.delete(String(key)),
        clear: () => persisted.clear(),
        key: index => [...persisted.keys()][index] ?? null,
        get length() { return persisted.size; },
      };
      Object.defineProperty(window, 'localStorage', { configurable: true, value: localStorage });
      window.alert = () => {};
      window.confirm = () => true;
    },
  });
  return dom;
}
function buttonByText(doc, label) {
  return [...doc.querySelectorAll('button,input[type=submit],input[type=button]')]
    .find(el => new RegExp(label, 'i').test((el.textContent || el.value || el.ariaLabel || '').trim()));
}
function addTask(page, text) {
  const { document, Event } = page.window;
  const input = document.querySelector('input[type=text],input:not([type]),textarea');
  if (!input) return false;
  input.value = text;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  const add = buttonByText(document, 'add|create');
  if (add) add.click();
  else if (input.form) input.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  return true;
}
function taskRow(doc, marker) {
  const options = [...doc.querySelectorAll('li,[data-task-id],[class*=task-item],[class*=taskItem]')];
  return options.find(el => el.textContent.includes(marker)) || null;
}
function visible(doc, marker) {
  const row = taskRow(doc, marker);
  if (!row) return false;
  let el = row;
  while (el && el.nodeType === 1) {
    const computed = doc.defaultView.getComputedStyle(el);
    if (el.hidden || computed.display === 'none' || computed.visibility === 'hidden') return false;
    el = el.parentElement;
  }
  return true;
}

const first = 'Write report 57391';
const second = 'Fix calendar 84213';
let dom;
try {
  dom = createPage();
  const doc = dom.window.document;
  check('app renders', Boolean(doc.body && doc.querySelector('input')));
  check('add controls exist', Boolean(buttonByText(doc, 'add|create') || doc.querySelector('form')));
  check('task A can be added', addTask(dom, first) && doc.body.textContent.includes(first));
  check('task B can be added', addTask(dom, second) && doc.body.textContent.includes(second));
  check('changes persisted', persisted.size > 0);

  const row = taskRow(doc, first);
  const checkbox = row?.querySelector('input[type=checkbox]') || null;
  const toggle = checkbox || [...(row?.querySelectorAll('button') || [])].find(b => /done|complete|finish/i.test(b.textContent));
  const persistedBeforeToggle = JSON.stringify([...persisted]);
  if (checkbox) {
    checkbox.click();
  } else toggle?.click();
  const storedChange = JSON.stringify([...persisted]) !== persistedBeforeToggle;
  const completionStyle = String(row?.className || '') + ' ' + String(row?.getAttribute('style') || '');
  check('completion control works', Boolean(toggle) &&
    Boolean(storedChange || checkbox?.checked || /done|complete|line-through/i.test(completionStyle)));

  const completedButton = buttonByText(doc, '^completed$|^done$');
  const activeButton = buttonByText(doc, '^active$|^pending$');
  check('completed filter present', Boolean(completedButton));
  check('active filter present', Boolean(activeButton));
  completedButton?.click();
  check('completed filter shows completed task', visible(doc, first));
  activeButton?.click();
  check('active filter shows active task', visible(doc, second));

  const allButton = buttonByText(doc, '^all$');
  allButton?.click();
  const deleteRow = taskRow(doc, first);
  const del = [...(deleteRow?.querySelectorAll('button') || [])].find(b => /delete|remove|trash|×|✕/i.test(b.textContent + ' ' + (b.title || '') + ' ' + (b.ariaLabel || '')));
  del?.click();
  check('delete removes task', Boolean(del) && !doc.body.textContent.includes(first));

  dom.window.close();
  const reloaded = createPage();
  check('survives reload', reloaded.window.document.body.textContent.includes(second));
  reloaded.window.close();
} catch (error) {
  errors.push(String(error.stack || error).slice(0, 1000));
} finally {
  if (dom) dom.window.close();
}

check('no runtime exceptions', errors.length === 0, errors.join('; '));
const result = {
  attribution: 'TRUSTED_EVALUATOR_ON_UNEDITED_MODEL_OUTPUT',
  checks: assertions,
  passed: assertions.length >= 12 && assertions.every(x => x.passed),
  errors,
};
console.log('S043-RESULT ' + JSON.stringify(result));
process.exit(result.passed ? 0 : 1);
