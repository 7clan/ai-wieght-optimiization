// Trusted Session-039 invariant contract evaluator. Executes only inside
// the Docker-only runner, never on the host with generated source code.
import { readFile } from 'node:fs/promises';

const MARK = 'S039-RESULT ';
const emit = (record) => process.stdout.write(MARK + JSON.stringify(record) + '\n');

try {
  const spec = JSON.parse(await readFile('/harness/task.json', 'utf8'));
  if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(spec.export_name) ||
      !Array.isArray(spec.cases) || spec.cases.length < 6 ||
      spec.cases.some(c => !Array.isArray(c.inputs) || c.inputs.length !== 2 ||
                   typeof c.expected !== 'boolean')) {
    emit({ pass: false, checks: [{ name: 'trusted-fixture-invalid', passed: false }] });
    process.exitCode = 1;
  } else {
    const mod = await import('file:///candidate/output.ts');
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
