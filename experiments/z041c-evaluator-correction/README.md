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

## 4. Longer code generation benchmark (measured)

`archagent/z041c/bench_long.py` + `bench_long_child.py` — original vs merged
(the merged checkpoint re-materialized byte-identically from the committed
adapter + frozen base: safetensors sha256 `fc743be4…ba06`, matching the 041B
manifest; merge re-verified 494,032,768 params, exactly 144/290 matrices
changed, max |ΔW| = 0.0016923). Protocol identical to 041B `bench_cpu`
wherever it applies: fp32 load, threads=2, greedy, seed 20261111, one-shot
isolated subprocess per run, peak RSS via getrusage. New: four trusted
teacher-authored longer-form prompts (neutral domains, archived with
sha256 in `bench/prompts.json`; NOT from any suite split) spanning React
component / Express API router / Python logic module / Prisma schema+
client, at budgets 512 and 1024; plus the exact 041B 128-token continuity
prompt, 3 trials per model. Raw outputs archived verbatim per run
(`bench/runs/`, attribution QWEN_GENERATED_RAW_UNEDITED).

**Environment:** matched to the 041B ledger exactly (torch 2.15.0+cpu,
transformers 4.57.6, peft 0.21.2, accelerate 1.15.0). A first pass under
transformers 4.57.1 produced identical texts (same EOS token counts, same
distinct-3 to 4 decimals) and was superseded pre-publication; the archived
runs are the 4.57.6 ones.

**Continuity control (041B anchor):** the 128-token prompt ends in natural
EOS at 10 tokens in BOTH sessions' environments; tokens/s mean — base
6.865 vs merged 6.882 this session (041B: 6.948 vs 6.95). Same regime,
environment-drift control holds.

**Longer generations (4 prompts per model per budget):**

| metric | base | merged |
|---|---|---|
| sustained tokens/s @512 / @1024 | 8.659 / 8.550 | 8.469 / 8.576 |
| natural-EOS runs @512 / @1024 | 1/4 / 2/4 | **3/4 / 4/4** |
| brace-balanced runs @512 / @1024 | 3/4 / 4/4 | 3/4 / 4/4 |
| distinct-3 mean @512 / @1024 | 0.459 / 0.422 | **0.868 / 0.852** |
| gen seconds mean @512 / @1024 | 54.3 / 93.5 | 40.5 / 48.9 |
| peak RSS (max over all runs) | 3,314.7 MiB | 3,314.9 MiB |
| model load (mean) | 0.96 s | 1.01 s |

Read: throughput and RAM are unchanged (the merge adds zero runtime cost,
now confirmed on long generations too). The behavioral difference is
termination: the base model degenerates into repetition collapse on longer
form-factor prompts — e.g. `react-parcel-pickup` @1024 is ~1,000 tokens of
the identical `import { useSearchParams } from "next/navigation";` line
(distinct-3 0.015) — while the merged model terminates its files naturally
(EOS 4/4 at 1024) with high text diversity (distinct-3 ≥ 0.71 on every
prompt). A spot-check of the merged react output shows a coherent,
balanced JSX file (with an in-file quality slip: a doubled identifier
`addParcelErrorBannerErrorBanner`), i.e. these are STRUCTURAL termination
metrics, not correctness verdicts — correctness remains the dev-split
evaluator's job (0/6 → 0/6 after the §3 erratum). No generalization claim:
4 prompts, one seed, greedy only.

## 5. Not done

- No additional training of any kind (per instruction).
- The 24-task holdout remains sealed; no holdout-adjacent content entered
  prompts, probes or benchmarks.
- No GPU/cloud/billable resources; no Docker claims.
