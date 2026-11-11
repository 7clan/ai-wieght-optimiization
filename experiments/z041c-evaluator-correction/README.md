# SESSION 041C — Duplicate-title evaluator correction + longer code generation benchmark

**Branch:** `exp/zai-041-coding-finetune` (all work confined to it; main and
every other branch untouched).
**Scope (user instruction Z2):** correct the duplicate-title evaluator,
benchmark longer code generation, NO additional training, keep the 24-task
holdout sealed (it stayed sealed this session — no read, no load, no use).

## 1. The corrected defect

The frozen v2 api-post-validation contract requires: *"Reject duplicate title
**within one [Parent]** with HTTP 409."* The 039B probe plan verified only the
first half (duplicate → 409); it never tested the scoping half. A candidate
implementing a **global** title-uniqueness check — a contract violation —
passed every probe. That is precisely how the Session-041B merged model's
single Track-B pass (`radiostation:api-post-validation`, BEHAVIOR_PASS) was
scored: its duplicate lookup was `findFirst({ where: { title } })` with no
transmitter scoping.

**Correction (additive amendment `041C-duplicate-title-scope`):**

- `archagent/s039/scenarios.py::oracle_cases_corrected` inserts one probe
  after `duplicate-title`: `duplicate-title-other-parent` — the same title
  used by a row under a DIFFERENT parent must be ACCEPTED (201, persist +1).
  Every other skill is a byte-identical pass-through. The frozen suite, the
  frozen v1 scenario-plan files and all other probes are untouched
  (unit-tested strict-superset invariant).
- `route_fixtures.task_spec` stages the corrected plan and discloses
  `case_amendment: "041C-duplicate-title-scope"` in the spec, the wrappers
  and every evidence record.
- New KNOWN-BAD control `post-global-duplicate-control.ts` (otherwise
  spec-faithful, globally scoped duplicate check) added to the control
  matrix (10 → 11 controls).
- Consistency fix of trusted teacher material: the s040 integration
  reference route's duplicate check is now parent-scoped (with
  `fk ?? null` normalization so a missing parent cannot silently widen the
  Prisma filter). Behavior-neutral on every existing probe — the integration
  `post-409` case submits a same-parent duplicate.

## 2. Oracle validation of the correction

- s039 matrix, host-smoke tier (trusted controls only, no model code):
  **11/11 oracles validated** (`controls/host-smoke-matrix.json`). The
  global-duplicate control fails on exactly `duplicate-title-other-parent`
  and nothing else; the spec-faithful positive control passes all probes.
- s040 matrix, restricted tier (unshare backend, trusted controls only):
  **15/15 oracles validated** in 53.0 s
  (`controls/s040-matrix-post-reference-scope-fix.json`).
- Repo test suite: **224 passed, 10 skipped, 17 subtests** (041B's 221 + 3
  new tests; nothing broken).

## 3. Honest re-score of the affected evidence

Adding a probe is monotone for FAIL verdicts; the only archived route
verdict that could change was the 041B merged Track-B PASS. Re-scored
byte-identically from the archived evidence (sha256-verified) inside the
restricted execution tier (`rescore/`):

| item | 041B (old evaluator) | 041C (corrected) |
|---|---|---|
| merged Track-B `radiostation:api-post-validation` | BEHAVIOR_PASS (10 probes) | **BEHAVIOR_FAIL** (11 probes; fails exactly `duplicate-title-other-parent`) |
| 041B Track-B headline | 1/6 | **0/6** (erratum) |

The merged model's one claimed cross-domain family gain on the dev split
was an artifact of the lenient probe. EXECUTION_FAILED 4→2 and the
vocabulary-lock 23→15 reductions in the 041B report are probe-independent
and stand as measured. `docs/ZAI_SESSION041B_REPORT.md` carries the erratum
addendum; the original evidence files are preserved unmodified.

## 4. Longer code generation benchmark

`archagent/z041c/bench_long.py` — original vs merged (LoRA-merged
checkpoint re-materialized from the committed adapter + frozen base, params
re-verified 494,032,768), fp32, threads=2, greedy, one-shot subprocess per
run (peak RSS via resource.getrusage). Trusted neutral prompts (authored
for this benchmark, not from any suite split) spanning four longer-form
coding shapes at 512/1024-token budgets. Metrics: sustained tokens/s, wall
seconds, peak RSS, natural-EOS vs truncation, brace balance, distinct-3
repetition. Full data: `bench/long-gen-bench.json`.

## 5. Not done

- No additional training of any kind (per instruction).
- The 24-task holdout remains sealed; no holdout-adjacent content entered
  prompts, probes or benchmarks.
- No GPU/cloud/billable resources; no Docker claims.
