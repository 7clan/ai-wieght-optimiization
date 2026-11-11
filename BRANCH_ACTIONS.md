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
