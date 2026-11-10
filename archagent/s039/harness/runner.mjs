// Trusted Session-039 invariant contract evaluator. Executes only inside
// the Docker-only runner, never on the host with generated source code
// (the optional S039_* path environment variables exist solely so the
// trusted harness itself can be smoke-tested outside Docker with trusted
// control fixtures; the Docker invocation never sets them).
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const HARNESS = process.env.S039_HARNESS ?? '/harness';
const CANDIDATE = process.env.S039_CANDIDATE ?? '/candidate/output.ts';
const MARK = 'S039-RESULT ';
// Bind the real stdout write before any candidate code can monkey-patch
// process.stdout.write to suppress the genuine verdict or spoof a fake one.
// (Session-039B hardening: candidate console writes can still add extra
// marker lines, which fail closed as NO_UNAMBIGUOUS_VERDICT upstream.)
const stdoutWrite = process.stdout.write.bind(process.stdout);
const emit = (record) => stdoutWrite(MARK + JSON.stringify(record) + '\n');

try {
  const spec = JSON.parse(await readFile(`${HARNESS}/task.json`, 'utf8'));
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(spec.export_name) ||
      !Array.isArray(spec.cases) || spec.cases.length < 6 ||
      spec.cases.some(c => !Array.isArray(c.inputs) || c.inputs.length !== 2 ||
                   typeof c.expected !== 'boolean')) {
    emit({ pass: false, checks: [{ name: 'trusted-fixture-invalid', passed: false }] });
    process.exitCode = 1;
  } else {
    const mod = await import(pathToFileURL(CANDIDATE).href);
    const func = mod[spec.export_name];
    const checks = [];
    if (typeof func !== 'function') {
      checks.push({ name: 'export-present', passed: false });
    } else {
      checks.push({ name: 'export-present', passed: true });
      for (const c of spec.cases) {
        let passed = false;
        try {
          const result = await func(...c.inputs);
          passed = result === c.expected;
        } catch (_) { /* report failure, never forward candidate traceback */ }
        checks.push({ name: String(c.name).slice(0, 80), passed });
      }
    }
    emit({ pass: checks.every(x => x.passed), checks });
  }
} catch (_) {
  emit({ pass: false, checks: [{ name: 'runtime-or-fixture-error', passed: false }] });
  process.exitCode = 1;
}
