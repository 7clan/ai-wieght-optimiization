# SESSION 041C — Duplicate-title evaluator correction + longer code generation benchmark

**Date:** 2026-11-11
**Branch:** `exp/zai-041-coding-finetune` (from `adf668f`, the SESSION041B
final commit; main and every other branch untouched)
**Mandate (user instruction Z2):** correct the duplicate-title evaluator;
benchmark longer code generation; **no additional training**; keep the
24-task holdout sealed until both models are finalized. All four points
executed literally — no training occurred, and the holdout was never
loaded, read or used (the s039 loader refusal was exercised again this
session by the existing unit suite).

---

## 1. The defect in the duplicate-title evaluator

The frozen v2 `api-post-validation` contract requires: *"Reject duplicate
title **within one [Parent]** with HTTP 409."* The 039B probe plan verified
only the first half: its `duplicate-title` case posts the seeded title
under the SAME parent and expects 409. Nothing probed the scoping half —
so a candidate implementing a **global** title-uniqueness check (ignoring
the parent scope) passed every probe, even though the same title under a
different parent must be ACCEPTED per the contract.

This is not hypothetical: the 041B merged model's single Track-B pass
(`radiostation:api-post-validation`, BEHAVIOR_PASS) was scored on exactly
such a globally scoped candidate — `findFirst({ where: { title } })` with
no transmitter scoping.

## 2. The correction (additive, freeze-discipline compliant)

- `archagent/s039/scenarios.py::oracle_cases_corrected` — a versioned
  amendment (`041C-duplicate-title-scope`) that inserts ONE probe directly
  after `duplicate-title`: `duplicate-title-other-parent` — title
  `"Amber"` (seeded under `parent-a`) submitted with `fk: "parent-b"`
  must return **201 with persist +1**. Every other skill is a
  byte-identical pass-through. The frozen suite files, the frozen v1
  scenario-plan files and all other probes are untouched (in-place edits
  would have violated the append-only scenario-plan drift checks; the
  amendment is unit-tested to be a strict order-preserving superset).
- `route_fixtures.task_spec` stages the corrected plan for every
  train/dev POST contract (12 of them) and discloses
  `case_amendment: "041C-duplicate-title-scope"` in the staged spec;
  the s039 wrapper and the s040 restricted-tier compat wrapper surface it
  in every evidence record.
- New KNOWN-BAD control
  `experiments/z039-zai-execution/controls/post-global-duplicate-control.ts`:
  byte-identical to the spec-faithful positive control except the
  duplicate lookup is globally scoped — the exact defect shape. The
  s039 control matrix grows 10 → 11 (3 positive / 8 negative).
- Trusted-material consistency fix: the s040 **integration reference
  route** (teacher-authored oracle backend) implemented the same global
  duplicate check; it is now parent-scoped with `fk ?? null`
  normalization (a missing parent compares against null-parent rows
  instead of silently widening the Prisma filter, which ignores undefined
  keys). Behavior-neutral on every existing probe — the integration
  `post-409` case submits a same-parent duplicate. The integration case
  plan itself is unchanged (the frontend cannot be probed on scoping
  through the reference route without new frozen cases).

## 3. Oracle validation of the correction

| gate | result |
|---|---|
| s039 control matrix, host-smoke tier (trusted controls only, no model code) | **11/11 oracles validated**; the global-duplicate control fails on EXACTLY `duplicate-title-other-parent` (12/13 checks pass); the spec-faithful positive control passes all 13 |
| s040 control matrix, restricted tier (unshare backend) — after the reference-route scope fix | **15/15 oracles validated** (53.0 s) |
| repo unit suite | **224 passed, 10 skipped, 17 subtests** (041B's 221 + 3 new tests; nothing broken) |

## 4. Honest re-score of the affected evidence

Adding a probe is monotone for FAIL verdicts, so the only archived route
verdict that could change was the 041B merged Track-B PASS — the only
PASS among all 8 archived route records. Re-scored byte-identically from
the archived evidence (staged candidate sha256-verified against the
041B record) inside the restricted execution tier
(`UNSHARE_USERNS_DISCLOSED`, 12.0 s):

| endpoint | 041B (old evaluator) | 041C (corrected) |
|---|---|---|
| merged Track-B `radiostation:api-post-validation` | BEHAVIOR_PASS (10 probes) | **BEHAVIOR_FAIL** (11 probes; fails exactly `duplicate-title-other-parent`) |
| 041B Track-B dev headline | 1/6 | **0/6** |

Consequences, stated plainly:

- The 041B headline "one genuine transfer signal" is **RETRACTED** — it
  was an artifact of the lenient probe. The LoRA Stage-1 experiment shows
  **no dev-split correctness gain** under the corrected evaluator.
- The probe-independent 041B findings stand unchanged: EXECUTION_FAILED
  4→2, vocabulary-lock 23→15, zero runtime overhead.
- `docs/ZAI_SESSION041B_REPORT.md` carries an appended ERRATUM section;
  the original 041B evidence files are preserved unmodified; the re-score
  record lives in `experiments/z041c-evaluator-correction/rescore/`.

## 5. Longer code generation benchmark (no training)

Environment matched to the 041B ledger exactly (torch 2.15.0+cpu,
**transformers 4.57.6**, peft 0.21.2, accelerate 1.15.0; a first pass
under 4.57.1 produced identical texts — same EOS token counts, same
distinct-3 to 4 decimals — and was superseded pre-publication).

The merged checkpoint was re-materialized from the committed adapter +
frozen base (base safetensors sha256 re-verified `aff8914e…a47f80`); the
merge reproduced the 041B merged safetensors **byte-identically**
(`fc743be4…ba06`, matching the 041B manifest; 144/290 matrices changed,
max |ΔW| = 0.0016923, params 494,032,768). The 041B manifest is preserved
verbatim; the rebuild's manifest is archived as
`experiments/z041c-evaluator-correction/merged-rebuild-manifest.json`.

Protocol: identical to 041B `bench_cpu` wherever it applies (fp32 load,
threads=2, greedy, seed 20261111, one-shot isolated subprocess per run,
getrusage RSS). New: four trusted teacher-authored longer-form prompts
(neutral domains — parcel pickup / parking garage / reading room / repair
shop — archived with sha256 in `bench/prompts.json`; NOT from any suite
split) at budgets 512/1024, plus the exact 041B 128-token continuity
prompt with 3 trials per model. 22 runs total, all archived verbatim.

| metric | base | merged |
|---|---|---|
| continuity tokens/s (128-token prompt, 3 trials) | 6.865 | 6.882 |
| sustained tokens/s @512 / @1024 | 8.659 / 8.550 | 8.469 / 8.576 |
| natural-EOS runs @512 / @1024 | 1/4 / 2/4 | **3/4 / 4/4** |
| distinct-3 mean @512 / @1024 | 0.459 / 0.422 | **0.868 / 0.852** |
| brace-balanced runs @512 / @1024 | 3/4 / 4/4 | 3/4 / 4/4 |
| peak RSS (max over all runs) | 3,314.7 MiB | 3,314.9 MiB |
| model load (mean) | 0.96 s | 1.01 s |

Findings, stated with their correct strength:

1. **Performance**: the merged checkpoint is performance-identical to the
   original on long generations too (throughput, RAM, load). This extends
   the 041B zero-overhead finding beyond the 128-token anchor.
2. **Termination (the substantive behavioral difference):** the base model
   collapses into repetition on longer form-factor prompts — e.g.
   `react-parcel-pickup` @1024 is ~1,000 repetitions of the identical
   import line (distinct-3 0.0147, raw text archived); the merged model
   terminates its files naturally (4/4 EOS at 1024) with high text
   diversity (distinct-3 ≥ 0.71 on every prompt). One SFT pass over its
   own verified outputs visibly stabilized long-form termination.
3. These are **structural metrics, not correctness verdicts**. The merged
   react output still contains an in-file quality slip (a doubled
   identifier `addParcelErrorBannerErrorBanner`), and the corrected
   dev-split correctness remains 0/6 → 0/6. No generalization claim: 4
   prompts, one seed, greedy only.

## 6. Integrity and boundaries

- **Holdout: sealed all session** (never loaded; loader refusals
  exercised by the unit suite; nothing holdout-adjacent entered prompts,
  probes, benchmarks or reports).
- Model-generated code executed ONLY inside the restricted execution
  tier (the re-score) or as pure text output (the benchmark — generation
  only, no execution). Trusted controls ran in the disclosed host-smoke
  tier (039B precedent) and the restricted tier respectively.
- Main and every other branch untouched; all work on
  `exp/zai-041-coding-finetune` (see `BRANCH_ACTIONS.md`).
- No training of any kind; no GPU/cloud/billable resources.
- Known toolchain note: the `.eval-deps` node_modules aggregate tree-hash
  recorded in 039B could not be re-derived in this sandbox (its exact
  aggregation method is not in-repo); integrity was verified instead via
  the committed lockfile (sha256 match) + `npm ci` + exact file count
  (6,825) — disclosed here rather than glossed.

## 7. Artifacts

- `archagent/z041c/` — rescore driver, benchmark parent + child (importable,
  seeded, resumable)
- `experiments/z041c-evaluator-correction/` — README, control matrices
  (11/11 + 15/15), re-score record + staged archived candidate,
  benchmark prompts, 22 run records, `long-gen-bench.json`
- `experiments/z041c-evaluator-correction/merged-rebuild-manifest.json` —
  byte-identical rebuild proof (the original 041B manifest is preserved
  verbatim inside `merged-checkpoint/`)
- `docs/ZAI_SESSION041B_REPORT.md` — appended ERRATUM
- tests: 3 new (amendment superset invariants, task_spec disclosure,
  wrapper evidence surfacing)

## 8. Not done

- No Stage-2/DPO, no further LoRA passes, no hyperparameter search
  (no-training mandate).
- No integration-evaluator scope probe (would require new frozen
  integration cases; out of the mandate's scope — the reference-route
  fix removes the defect from the trusted oracle backend).
- No holdout evaluation: the three-way ceremony (original vs
  weight-edited vs fine-tuned) still awaits the user's unlock once the
  other agent's weight-edited checkpoint is frozen; the fine-tuned
  checkpoint remains frozen for exactly that.
