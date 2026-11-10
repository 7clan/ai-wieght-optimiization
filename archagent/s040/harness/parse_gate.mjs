// TRUSTED Session-040 parse gate — AUTHORED_GATE_NOT_QWEN_CODE
// Syntax-level gate for app pieces whose behavioral oracle is the Phase-6
// app-level test suite: transpiles the candidate with the pinned esbuild
// (transform only — the candidate is never executed) and reports one
// fail-closed S040-RESULT verdict.
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const DEPS = '/eval-deps';
const MARK = 'S040-RESULT ';
const emit = (record) => process.stdout.write(MARK + JSON.stringify(record) + '\n');
const checks = [];
const ok = (name) => checks.push({ name, passed: true });
const fail = (name, detail) => checks.push({ name, passed: false, detail: String(detail).slice(0, 240) });

try {
  const spec = JSON.parse(await readFile(`${process.env.HARNESS || '/harness'}/task.json`, 'utf8'));
  const loader = spec.loader === 'tsx' ? 'tsx' : 'ts';
  const file = spec.candidate_file || 'output.ts';
  const source = await readFile(`/candidate/${file}`, 'utf8').catch(() => null);
  if (source === null) {
    fail('candidate-readable', `missing /candidate/${file}`);
  } else {
    const req = createRequire(`${DEPS}/`);
    const esbuild = req('esbuild');
    try {
      await esbuild.transform(source, { loader, format: 'esm', target: 'node20' });
      ok('candidate-parses');
    } catch (error) {
      fail('candidate-parses', error.errors ? error.errors[0]?.text : String(error));
    }
  }
} catch (error) {
  fail('gate-error', error instanceof Error ? error.message : String(error));
}
const pass = checks.length > 0 && checks.every((c) => c.passed);
emit({ pass, checks });
process.exitCode = 0;
