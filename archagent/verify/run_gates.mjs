// SESSION 036 — PHASE 1 (TRUSTED-SCAFFOLD).
// CLI for the structural gate engine.
//
//   node run_gates.mjs --contract contract.json [--root DIR] [--stdin]
//
// contract.json: { kind, file, handlers/calls/..., instruction? }
// With --stdin the code is read from stdin (pre-install gating from the
// Python harness); otherwise the file is read relative to --root.
// Output: single-line JSON verdict on stdout.

import fs from 'node:fs';
import path from 'node:path';
import { verifyFile, verifyInterfaces, verifyPrisma } from './gates.mjs';

const args = process.argv.slice(2);
function argOf(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

const contractPath = argOf('--contract');
const root = argOf('--root') || '/home/z/my-project';
const useStdin = args.includes('--stdin');

let contract;
try {
  contract = JSON.parse(fs.readFileSync(contractPath, 'utf8'));
} catch (e) {
  console.log(JSON.stringify({ pass: false, failures: [`contract unreadable: ${e}`] }));
  process.exit(2);
}

let result;
if (contract.kind === 'interfaces') {
  result = verifyInterfaces(root, contract.checks);
} else if (useStdin) {
  const code = fs.readFileSync(0, 'utf8');
  result = verifyFile(code, contract, contract.file || 'file.ts');
} else {
  const p = path.join(root, contract.file);
  try {
    const code = fs.readFileSync(p, 'utf8');
    result = verifyFile(code, contract, contract.file);
  } catch (e) {
    result = { pass: false, failures: [`file unreadable: ${String(e).slice(0, 120)}`] };
  }
}
console.log(JSON.stringify(result));
process.exit(result.pass ? 0 : 1);
