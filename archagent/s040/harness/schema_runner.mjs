// Trusted Session-040 schema-relationship evaluator runner. Executes ONLY
// inside the restricted execution tier. Normalizes a COPY of the candidate's
// Prisma schema (datasource url + generator output redirected to /work; the
// candidate file itself is never modified), builds a fresh SQLite database
// from it with the pinned schema engine, generates the client, and probes
// the RELATIONAL BEHAVIOR the frozen v2 contract requires: required fields,
// valid-FK create, FK nullability, bogus-FK rejection, onDelete semantics
// (SetNull for optional FK, Restrict for required FK) and the persisted
// status default. Emits exactly one S040-RESULT verdict; fail-closed.
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

const run = promisify(execFile);
const MARK = 'S040-RESULT ';
const stdoutWrite = process.stdout.write.bind(process.stdout);
const emit = (record) => stdoutWrite(MARK + JSON.stringify(record) + '\n');

const HARNESS = process.env.S040_HARNESS ?? '/harness';
const CANDIDATE = process.env.S040_CANDIDATE ?? '/candidate/output.prisma';
const WORK = process.env.S040_WORK ?? '/work';
const WATCHDOG_MS = Number(process.env.S040_WATCHDOG_MS ?? 150_000);

let checks = [];
let done = false;
const finish = (pass, status) => {
  if (done) { process.exit(1); }
  done = true;
  emit({ pass, checks, status });
  process.exit(0);
};
const watchdog = setTimeout(() => finish(false, 'watchdog-timeout'), WATCHDOG_MS);
watchdog.unref?.();
const fail = (name, detail) => { checks.push({ name, passed: false, detail: String(detail).slice(0, 200) }); };
const ok = (name) => { checks.push({ name, passed: true }); };

async function prismaStep(args) {
  try {
    await run('prisma', args, { cwd: WORK, env: { ...process.env, PRISMA_HIDE_UPDATE_MESSAGE: '1' } });
  } catch (error) {
    const detail = `rc=${error.code} | out: ${String(error.stdout || '').slice(0, 150)} | err: ${String(error.stderr || '').slice(-300)}`;
    throw new Error(detail);
  }
}

async function main() {
  const spec = JSON.parse(await readFile(`${HARNESS}/task.json`, 'utf8'));
  const parent = spec.entities.parent;
  const child = spec.entities.child;
  const fk = spec.entities.foreign_key;
  const fkOptional = spec.entities.foreign_key_optional;
  const label = spec.fields.label;
  const amount = spec.fields.amount;
  const lo = spec.fields.min_inclusive;
  const initialStatus = spec.workflow[0];
  const source = await readFile(CANDIDATE, 'utf8');

  // Static sanity: both models and the FK field must be present.
  if (!new RegExp('model\\s+' + parent + '\\b').test(source)) { fail('parent-model-present', 'model ' + parent + ' missing'); return finish(false, 'static-fail'); }
  if (!new RegExp('model\\s+' + child + '\\b').test(source)) { fail('child-model-present', 'model ' + child + ' missing'); return finish(false, 'static-fail'); }
  if (!source.includes(fk)) { fail('fk-field-present', 'field ' + fk + ' missing'); return finish(false, 'static-fail'); }
  ok('models-and-fk-present');

  // Normalize a COPY: sqlite url + generated client location + library engine.
  // Candidates may use env("DATABASE_URL") or omit output/engineType entirely;
  // every variant is redirected so the generated client lands in writable /work.
  let normalized = source
    .replace(/url\s*=\s*(?:"[^"]*"|env\([^)]*\))/, 'url = "file:/work/db.sqlite"')
    .replace(/output\s*=\s*"[^"]*"/, 'output = "/work/generated-client"')
    .replace(/engineType\s*=\s*"[^"]*"/, 'engineType = "library"');
  if (!/provider\s*=\s*"sqlite"/.test(normalized)) {
    normalized = normalized.replace(/datasource\s+db\s*\{/, 'datasource db {\n  provider = "sqlite"');
  }
  if (!/output\s*=\s*"/.test(normalized)) {
    normalized = normalized.replace(/generator\s+client\s*\{/, 'generator client {\n  output = "/work/generated-client"');
  }
  if (!/engineType\s*=\s*"/.test(normalized)) {
    normalized = normalized.replace(/generator\s+client\s*\{/, 'generator client {\n  engineType = "library"');
  }
  await mkdir(`${WORK}/lib`, { recursive: true });
  await writeFile(`${WORK}/schema.prisma`, normalized, 'utf8');
  await copyFile(`${HARNESS}/probe.mjs`, `${WORK}/probe.mjs`);

  try {
    await prismaStep(['db', 'push', '--schema', `${WORK}/schema.prisma`, '--skip-generate', '--accept-data-loss']);
  } catch (error) {
    fail('schema-builds', error.message); return finish(false, 'schema-invalid');
  }
  ok('schema-builds');
  try {
    await prismaStep(['generate', '--schema', `${WORK}/schema.prisma`]);
  } catch (error) {
    fail('client-generates', error.message); return finish(false, 'generate-failed');
  }
  ok('client-generates');

  // Behavioral probes against the candidate-built database.
  const { runProbes } = await import(pathToFileURL(`${WORK}/probe.mjs`).href);
  const verdict = await runProbes({
    parentClient: parent.toLowerCase(), childClient: child.toLowerCase(),
    fk, fkOptional, label, amount, lo, initialStatus,
  });
  for (const probe of verdict.probes) {
    if (probe.passed) { ok(probe.name); } else { fail(probe.name, probe.detail); }
  }
  const pass = checks.length > 0 && checks.every((c) => c.passed);
  return finish(pass, pass ? 'all-probes-passed' : 'probe-failures');
}

main().catch((error) => { fail('runner-error', error instanceof Error ? error.stack : String(error)); finish(false, 'runner-error'); });
