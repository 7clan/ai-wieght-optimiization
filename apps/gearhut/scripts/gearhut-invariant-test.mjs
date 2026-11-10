// SESSION040 GearHut — invariant unit test: the 7-case frozen table from
// APP_SPEC.json §invariant_contract.cases, run against the INTEGRATED
// src/lib/gear-invariant.ts (QWEN-REPAIRED bytes). TRUSTED test code.
import { canAdvanceGearItem } from '../src/lib/gear-invariant.ts'

const cases = [
  { name: 'stashed-with-locker', inputs: [{ status: 'stashed', usageHours: 5 }, { id: 'l1' }], expected: true },
  { name: 'stashed-null-locker', inputs: [{ status: 'stashed', usageHours: 5 }, null], expected: false },
  { name: 'inspected-in-range', inputs: [{ status: 'inspected', usageHours: 100 }, { id: 'l1' }], expected: true },
  { name: 'inspected-below-range', inputs: [{ status: 'inspected', usageHours: 0 }, { id: 'l1' }], expected: false },
  { name: 'inspected-above-range', inputs: [{ status: 'inspected', usageHours: 2001 }, { id: 'l1' }], expected: false },
  { name: 'retired-terminal', inputs: [{ status: 'retired', usageHours: 10 }, { id: 'l1' }], expected: false },
  { name: 'unknown-status', inputs: [{ status: 'flying', usageHours: 10 }, { id: 'l1' }], expected: false },
]

let failed = 0
for (const c of cases) {
  const got = canAdvanceGearItem(c.inputs[0], c.inputs[1])
  const ok = got === c.expected
  if (!ok) failed++
  console.log(`  ${ok ? 'ok' : 'FAIL'} ${c.name} (expected ${c.expected}, got ${got})`)
}
console.log(`\ninvariant suite: ${cases.length - failed} passed, ${failed} failed`)
process.exit(failed ? 1 : 0)
