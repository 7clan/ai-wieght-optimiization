# Branch Action Ledger — `exp/zai-041-coding-finetune`

This file is the per-branch action ledger. It exists **only on the
branch named in the title**, so its very presence identifies the
branch you are looking at:

    git show exp/zai-041-coding-finetune:BRANCH_ACTIONS.md  # exists (this file)
    git show main:BRANCH_ACTIONS.md                          # errors

Every commit created from an action in this ledger also carries the
prefix `[exp/zai-041-coding-finetune]` in its subject.

## Branch facts

- Branch: `exp/zai-041-coding-finetune`
- Forked from: `exp/zai-040-autonomous-fullstack` @ `84dbc39`
  (the SESSION040 final commit) on 2026-11-11
- Scope guarantee: no action in this ledger writes to any other branch
  or to `main`; every push goes to `origin/exp/zai-041-coding-finetune`
  only
- Authorization: the 041B session brief explicitly permits ONE limited
  LoRA fine-tuning experiment on this branch, superseding the standing
  no-training rule here only
- Work: SESSION 041B — execute the SESSION040 training proposal Stage 1
  (LoRA SFT on the 25 verified model-origin candidates), merge into the
  frozen checkpoint, verify architecture/parameter count, measure
  before/after coding correctness and CPU performance

## Ledger

Rows are append-only. The "Commit" column records the commit that
contains the action; a row is filled in by the next ledger update, so
the newest row may still say "this commit".

| # | UTC time | Action | Outcome | Commit |
|---|----------|--------|---------|--------|
| 1 | 2026-11-11T00:05Z | Branch created at `84dbc39`; environment restored on the recycled sandbox (torch 2.15.0+cpu, transformers 4.57.6, peft 0.21.2, accelerate 1.15.0; `.eval-deps` npm ci from the pinned lockfile); frozen model re-verified (safetensors sha `aff8914e…a47f80`) | Environment ready | this commit |
| 2 | 2026-11-11T00:20Z | Restricted-tier control matrix re-validated BEFORE any candidate scoring (15/15 oracles, unshare backend, 49.6 s); repo unit suite 221 passed / 10 skipped | Tier + oracles green | this commit |
| 3 | 2026-11-11T00:35Z | 25 verified candidates audited: 038A 22 + 040 3, sha256 chain 25/25 (prompts + candidates), contamination scan 0 violations, holdout seal refusal re-verified (never loaded) | Dataset sources verified | this commit |
| 4 | 2026-11-11T00:45Z | Dataset built (`dataset/sft-25.jsonl`): anchor-overlap boundary rule, token-boundary integrity asserted, family-weighted 300-draw plan (seed 4141); dtype probe: bf16 4.9 s/micro-step (fp32 not measurable — OOM) → bf16 trunk per 038A plan | Dataset frozen | this commit |
| 5 | 2026-11-11T01:00–01:25Z | ONE budget-limited LoRA run: 37/37 optimizer steps (296 micro), 1,292.5 s of the 2,400 s cap, peak RSS 2,272 MiB, seed 4141, resumable across 4 sandbox invocations with per-step checkpointing; loss ~0.02–0.075 → ~0.001–0.002 (training-set memorization, disclosed) | `train/` complete, plan-complete | this commit |
| 6 | 2026-11-11T01:30Z | Merge via `merge_and_unload()`: 494,032,768 params / 24 layers / 896 hidden verified, exactly 144/290 matrices changed (LoRA targets only), config+tokenizer byte-identical to the original (first save had transformer re-serialization drift — found, fixed with verbatim copies, re-merged, re-verified) | `merged-checkpoint/` frozen | this commit |
| 7 | 2026-11-11T01:40–02:10Z | Paired before/after eval, dev split (radiostation, 6 tasks × Tracks A/B, identical prompts/seeds/evaluators as S040, restricted tier): A 0/6→0/6, B 0/6→**1/6** (api-post-validation, restricted-tier BEHAVIOR_PASS), EXECUTION_FAILED 4→2, Track-B vocab-lock 23→15; base re-run reproduced the archived 040 dev results (environment control) | Eval frozen; pre-declared Stage-1 criteria NOT met (reported as-is) | this commit |
| 8 | 2026-11-11T02:15Z | CPU benchmarks (3 isolated trials each): load 0.83 vs 0.86 s, 6.95 vs 6.95 tok/s, peak RSS 3,309.6 vs 3,308.8 MiB — merged checkpoint performance-identical | `bench/cpu-bench.json` | this commit |
| 9 | 2026-11-11T02:20Z | Session report + ledger + adapter committed (merged weights gitignored per repo convention; merge reproducible from committed adapter + frozen base); branch pushed | SESSION 041B complete; budget stopped after the one authorized experiment | this commit |
| 10 | 2026-11-11T03:05Z | SESSION 041C start (user instruction Z2): duplicate-title evaluator defect found — the 039B probe plan verified duplicate→409 but never the "within ONE parent" scoping half of the frozen contract, so GLOBALLY scoped duplicate checks passed (this is how the 041B merged Track-B PASS was scored); environment restored on the recycled sandbox (torch 2.15.0+cpu, transformers 4.57.6, peft 0.21.2, accelerate 1.15.0; `.eval-deps` npm ci from the pinned lockfile, 6,825 files, lockfile sha verified); frozen base re-verified (`aff8914e…a47f80`) | Defect isolated; env ready | this commit |
| 11 | 2026-11-11T03:10Z | Additive amendment `041C-duplicate-title-scope`: `oracle_cases_corrected` inserts `duplicate-title-other-parent` (same title under a different parent → 201, +1) after `duplicate-title`; frozen suite + frozen v1 scenario plans untouched (unit-tested strict order-preserving superset); amendment disclosed in task_spec, both evaluator wrappers and every evidence record; new KNOWN-BAD control `post-global-duplicate-control.ts` (s039 matrix 10→11); s040 integration reference route parent-scoped (`fk ?? null`), behavior-neutral on every existing probe | Correction staged | this commit |
| 12 | 2026-11-11T03:20Z | Corrected-evaluator oracle validation: s039 host-smoke matrix **11/11** (the global-duplicate control fails on EXACTLY the new probe; spec-faithful positive passes all 13); s040 restricted tier (unshare) **15/15** in 53.0 s; repo unit suite 224→ then 231 passed (7 new z041c tests added later), 0 broken | Oracles green | this commit |
| 13 | 2026-11-11T03:25Z | Honest re-score of the ONE affected archived verdict (the only route PASS; adding a probe is monotone for FAILs): staged candidate sha-verified against the 041B record, re-evaluated in the restricted tier (12.0 s) → **BEHAVIOR_FAIL**, fails exactly `duplicate-title-other-parent`; 041B Track-B headline corrected 1/6 → **0/6**; ERRATUM appended to `docs/ZAI_SESSION041B_REPORT.md` (original text preserved); "one genuine transfer signal" claim RETRACTED; probe-independent 041B findings (EXECUTION_FAILED 4→2, vocab-lock 23→15, zero runtime overhead) stand | Affected evidence corrected | this commit |
| 14 | 2026-11-11T03:30Z | Longer code generation benchmark (no training): merged checkpoint re-materialized from the committed adapter + frozen base — merge reproduced the 041B safetensors BYTE-IDENTICALLY (`fc743be4…ba06`, 144/290 matrices, max |ΔW| 0.0016923); 041B manifest preserved, rebuild manifest archived; 22 runs (4 teacher-authored neutral longer-form prompts × budgets 512/1024 × both models + the 041B 128-token continuity prompt × 3 trials each), one-shot subprocesses, fp32/threads=2/greedy/seed 20261111, transformers matched to the 041B pin 4.57.6 (a 4.57.1 first pass produced identical texts and was superseded pre-publication, disclosed) | `bench/` complete | this commit |
| 15 | 2026-11-11T03:35Z | Benchmark results: throughput/RAM identical (sustained 8.47–8.66 tok/s both; peak RSS 3,314.7 vs 3,314.9 MiB; load 0.96 vs 1.01 s; continuity 6.865 vs 6.882 tok/s vs 041B's 6.95/6.95 — drift control holds); substantive behavioral difference = termination: base repetition-collapses on long prompts (distinct-3 as low as 0.015, raw texts archived), merged terminates naturally (EOS 3/4 @512, 4/4 @1024; distinct-3 ≥ 0.71) — structural metrics only, NOT correctness verdicts (corrected dev-split stays 0/6→0/6) | `long-gen-bench.json` + report written | this commit |
| 16 | 2026-11-11T03:40Z | Session 041C report (`docs/ZAI_SESSION041C_EVALUATOR_CORRECTION_LONGBENCH.md`) + experiment README + 7 new unit tests (231 passed / 10 skipped / 17 subtests total); holdout still sealed (loader refusals exercised; never loaded); no training, no GPU/cloud spend; branch pushed | SESSION 041C complete within mandate | this commit |
| 17 | 2026-11-11T10:30Z | RECOVERY (both Z environments reset before the 041C push; row 16's "branch pushed" was premature — remote still stood at `adf668f`): recovered artifacts verified — `session041c-commits.bundle` okay, requires exactly `adf668f`, contributes the two original commits `a874d9b` (= PATCH 1/2) + `550a337` (= PATCH 2/2); standalone patch files, 041C report and experiment README all byte-identical to the commits; 041B checkpoint hash-parity — adapter tarball (all 10 files), merge-manifest, train/bench/eval artifacts byte-identical to committed state, base safetensors `aff8914e…a47f80`, 041B report == `adf668f` version (550a337 adds only the erratum); security scan of both commits: 0 token patterns, no credential files, no holdout paths touched; unit suite (fresh sandbox, no torch): 28/28 on the 041C-touched test files, 180 passed / 10 skipped / 13 subtests overall excluding the 7 torch-dependent legacy files (byte-unchanged by 041C, covered by the archived 231-passed pinned-env run); branch fast-forwarded to the ORIGINAL `550a337` (nothing re-applied) + this recovery record; pushed | Recovery complete; PATCH 1/2 recovered intact from the bundle — no reconstruction needed | this commit |
