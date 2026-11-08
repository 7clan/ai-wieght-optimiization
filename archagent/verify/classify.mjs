// SESSION 036 — PHASE 1 (TRUSTED-SCAFFOLD).
// Error classification for dynamic tests: an application error is a
// defect of the code under test; a harness error is a defect of the test
// machinery itself (Session 035's NaN comparisons, strict-mode duplicate
// queries, self-inflicted outage counting).  They must never be conflated.
//
// classify(err, context) -> { kind, label, detail }
//   kind 'app'     — the application under test misbehaved
//   kind 'harness' — the test machinery misbehaved (never counts against
//                    the application; logged and fixed with disclosure)
//   kind 'unknown' — cannot be attributed; treated as harness-suspect
//                    (conservative: does not count against the app until
//                    a human/teacher triages)

const HARNESS_SIGNATURES = [
  { re: /TypeError: .* is not a function.*node_modules\/playwright|page\.|locator/i,
    kind: 'harness', why: 'playwright API misuse in the test' },
  { re: /ERR_CONNECTION|ECONNREFUSED|fetch failed/i,
    kind: 'app', why: 'application server unreachable/refused' },
  { re: /Timeout .*exceeded.*expect/i,
    kind: 'app', why: 'expected application state never appeared' },
  { re: /TypeError: Cannot read properties of (undefined|null)/i,
    kind: 'app', why: 'application returned unexpected shape' },
];

// numeric sanity: a comparison that produced NaN is ALWAYS a harness bug
// (Session 035 defect #14: unawaited .count() promises compared as NaN).
export function isNanComparison(a, b) {
  const na = typeof a === 'number' ? a : NaN;
  const nb = typeof b === 'number' ? b : NaN;
  return Number.isNaN(na) || Number.isNaN(nb);
}

export function classify(err, context = '') {
  const detail = err && err.stack ? String(err.stack).split('\n').slice(0, 3).join(' | ')
    : String(err);
  for (const sig of HARNESS_SIGNATURES) {
    if (sig.re.test(detail) || sig.re.test(context)) {
      return { kind: sig.kind, label: sig.why, detail: detail.slice(0, 300) };
    }
  }
  // thrown inside our own runner files => harness
  if (/at .*archagent[\\/]|at .*apitest|at .*uitest|at TestSuite/.test(detail)) {
    return { kind: 'harness', label: 'stack passes through harness frames',
      detail: detail.slice(0, 300) };
  }
  return { kind: 'unknown', label: 'unattributed failure — triage required',
    detail: detail.slice(0, 300) };
}
