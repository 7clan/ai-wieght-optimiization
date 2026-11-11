# SESSION 041B — Qwen Coding Fine-Tuning (LoRA Stage 1, executed)

**Date:** 2026-11-11
**Branch:** `exp/zai-041-coding-finetune` (from `84dbc39`, the SESSION040 final commit)
**Authorization:** the user explicitly permitted ONE limited LoRA fine-tuning
experiment in the 041B session brief. This supersedes the standing no-training
rule **on this branch only** (AGENTS.md §Objective; the 038A "graduation rule"
condition (b) — explicit user authorization of a training branch — is now met).
**Model:** frozen `Qwen/Qwen2.5-Coder-0.5B`, safetensors sha256
`aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`
(re-verified before training and before the merge; architecture check
494,032,768 params / 24 layers / 896 hidden on every load).
**Hardware reality:** no GPU exists in this sandbox (2 vCPU, 3.9 GiB RAM,
no Docker — same class as every prior session). The run was a **bounded,
disclosed CPU experiment**: hard caps of 37 optimizer steps / 2,400 s
cumulative training time, checked every micro-step. It was NOT an unbounded
CPU substitution; the caps are recorded in `train-config.json` and the run
finished at 1,292.5 s (54% of the cap).

---

## 1. Executive summary

1. **The experiment ran, within budget, end-to-end on CPU**: dataset →
   LoRA training (37 optimizer steps, 1,292.5 s, peak RSS 2.27 GiB) → real
   `merge_and_unload()` → verified merged checkpoint → paired before/after
   evaluation in the restricted execution tier → CPU benchmarks.
2. **The merged checkpoint is verified architecture-identical**:
   `Qwen2ForCausalLM`, 494,032,768 parameters, 24 layers, 896 hidden; config
   and tokenizer files byte-identical to the original; exactly 144 of 290
   weight matrices changed (24 layers × the 6 LoRA target modules — nothing
   else moved); max |ΔW| = 0.00169, max relative change 1.4%.
3. **Coding correctness moved on Track B but not Track A** (dev split,
   radiostation, 6 tasks, identical prompts/seeds/evaluators as Session 040):
   Track-A 0/6 → 0/6; **Track-B 0/6 → 1/6** — a full restricted-tier
   BEHAVIOR_PASS on `radiostation:api-post-validation`, a skill family the
   training set contained (3 verified POST-route examples from other
   domains: observatory + gearhut). EXECUTION_FAILED (crashes) halved:
   4 → 2 of 12 pairs. Demo-vocabulary copying decreased but persisted:
   23 → 15 greenhouse-noun occurrences (3/6 candidates both times).
4. **The pre-declared Stage-1 success criteria were NOT met** (TRAINING_
   PROPOSAL.md §5.5: Track-A dev ≥ 2/6; vocabulary-lock = 0 on ≥ 5/6
   candidates). Reported as-is, per the frozen plan. The single-track-B
   gain is a real measured effect on a task family present in training —
   a domain-transfer signal, **not** a broad-generalization claim.
5. **Zero runtime overhead**: original vs merged — 0.83 s vs 0.86 s load,
   6.95 vs 6.95 tokens/s, 3,309.6 vs 3,308.8 MiB peak RSS (3 isolated
   trials each, identical protocol).

## 2. The dataset (audit → build)

- **Audit:** all 25 verified model-origin candidates resolved to their
  archived evidence records with a **perfect sha256 chain** (25/25 candidate
  hashes match, 25/25 prompt hashes match, 25 distinct prompts, 25 distinct
  candidates): the 038A 22 (z037 curricula/challenge; families:
  relations-parent-1tm ×10, relations-child-required-fk ×7, singletons ×5)
  plus the 040 3 (`s040-B-observatory-api-post-validation`,
  `s040-APP-gearhut-invariant`, `s040-APP-gearhut-api-post-validation`).
- **Boundary rule:** the supervised completion is exactly what the model
  generated — the harness anchor overlap (z040-era records embed the anchor
  in the candidate) is stripped mechanically; z037-era records carry no
  overlap. Token-boundary integrity asserted per example (prompt token ids
  are a strict prefix of the full sequence's ids).
- **Contamination guards (fail-closed):** split tags ∈ {train, app} only;
  dev-domain vocabulary scan (radiostation/tailorshop/sportsarena + field
  nouns) over all prompts+completions: **0 violations**. The 24 holdout
  tasks stayed sealed the entire session (the s039 loader refuses the
  holdout split; refusal re-verified; no read occurred).
- **Family weighting (038A mandatory rule):** 300 draws with replacement,
  weight ∝ 1/family_count → 18–41 draws per family (vs the raw 1–10 skew).
- **Disclosed amendments** (pre-registered in `train-config.json`): epochs
  3 → 12 (038A Plan-1 used 20; 12 fits its measured time envelope), one
  supervised EOS token per completion, 296 of 300 draws (grad-accum tail),
  bf16 trunk per the measured dtype probe.

## 3. Training (one controlled run)

| item | value |
|---|---|
| LoRA | r=16, α=32, dropout 0.05, bias none, targets q/k/v/o + up/down (24 layers × 6 = 144 modules, 6,586,368 trainable params, fp32 adapters on bf16 trunk) |
| Optimization | AdamW, lr 2e-4 cosine (inside the proposal's 1e-4..2e-4), no warmup, micro-batch 1, grad-accum 8 (effective batch 8) |
| Loss | CE on completion tokens + 1 EOS only (prompt masked −100); chunked lm_head+CE (128-position chunks; the full fp32 logit tensor would need ~1.5 GiB) |
| Seed | 4141 (sampler, torch, init) |
| Steps | 37 optimizer / 296 micro of 37/296 planned — **plan-complete** |
| Time | 1,292.5 s cumulative (cap 2,400 s) |
| RAM | 2,272.5 MiB peak |
| Loss trajectory | batch-mean CE ~0.02–0.075 early → ~0.001–0.002 late (training-set memorization — expected for SFT on the model's own verified outputs; **no generalization claim is made from it**) |
| Resumability | checkpoint (adapter + optimizer + scheduler + rng + position) after every optimizer step; the sandbox reaps detached processes and caps tool calls at 10 min, so the run completed across 4 invocations with identical math |

`train-log.jsonl` records every optimizer step (loss, lr, elapsed, RSS).
The full log, config and summary are under `experiments/z041-coding-finetune/train/`.

## 4. Merge and verification (user-mandated checks)

`archagent/z041/merge_verify.py`: load base fp32 → load adapter →
`merge_and_unload()` → verify → save bf16.

- Class after merge: `Qwen2ForCausalLM` (no adapter modules remain).
- **Parameter count: 494,032,768 — identical to the original.** 24 layers,
  896 hidden, vocab unchanged; all weights finite.
- Weight-diff audit (against the on-disk base, memory-mapped, exact):
  **exactly 144 matrices changed = 24 × 6 LoRA targets; 146 matrices
  byte-identical**; max |ΔW| = 0.00169; largest relative change 1.40%.
- The merged directory is byte-identical to the original in every file
  **except `model.safetensors`** (config, generation_config, tokenizer
  files copied verbatim — a transformers 4.57 re-save alters
  tokenizer.json bytes and rewrites config keys, measured and disclosed;
  tokenization equality asserted explicitly).
- Merged weights are NOT committed to git (repo convention: `*.safetensors`
  ignored; GitHub 100 MB/file limit). The adapter IS committed, so the
  merge reproduces deterministically from branch artifacts:
  `ARCHAGENT_MODEL_DIR=<frozen base> python -m archagent.z041.merge_verify`.
  Full manifest with every sha256: `merged-checkpoint/merge-manifest.json`.

## 5. Before/after coding correctness (frozen plan primary endpoints)

Protocol: SESSION040's exactly — dev split (radiostation, 6 tasks, one per
skill), Tracks A (unassisted) and B (contract-first), greedy decoding, the
same hash-derived seeds, L-TRIM extraction + forced-continuation retry, the
same six evaluator families inside the restricted execution tier
(UNSHARE_USERNS_DISCLOSED; 15/15 oracle controls re-validated first,
49.6 s), fail-closed verdicts, vocabulary-lock counter on the 040 taxonomy
word list. Evidence: `experiments/z041-coding-finetune/eval/{base,merged}/`.

| endpoint | base (frozen) | merged | Δ |
|---|---|---|---|
| Track-A pass@1 (dev) | 0/6 | 0/6 | — |
| Track-B pass@1 (dev) | 0/6 | **1/6** | +1 (`api-post-validation`) |
| EXECUTION_FAILED (A+B) | 4/12 | 2/12 | −2 |
| vocab-lock violations, Track B | 23 (3/6 candidates) | 15 (3/6 candidates) | −8 |
| gen tokens (A+B) | 4,602 | 4,761 | +3% |

- The pass is a full restricted-tier behavioral pass (route evaluator,
  fail-closed) on a task family that had 3 training examples from OTHER
  domains — the model bound the dev task's own nouns (vocab-lock = 0 on
  that candidate). This is the session's one genuine transfer signal.
- The base re-run on this recycled sandbox reproduced Session 040's
  archived dev results exactly (A 0/6, B 0/6) — the environment-drift
  control holds; the comparison is paired on identical seeds.
- **Pre-declared success criteria: NOT met** (Track-A ≥ 2/6 required;
  vocab-lock 0 on ≥ 5/6 required). Reported as-is per TRAINING_PROPOSAL
  §5.5. No regression appeared on any dev endpoint.
- Honest limitations: 25 examples is a pilot; the gain is confined to a
  trained family; demo-vocabulary copying persists at reduced magnitude;
  the 038A-suite (orchard/marina/bakery) regression re-run could NOT be
  executed because the z038a harness installs into the Session-036-era
  Next.js workspace, which does not exist in this recycled sandbox (the
  dev-split schema/invariant pairs — both 0/6 → 0/6 — are the available
  proxy for the 038A families).

## 6. CPU performance benchmarks (user-mandated)

`archagent/z041/bench_cpu.py` — 3 isolated one-shot subprocess trials per
model, identical protocol (fp32 load — the harness path — threads=2, greedy,
128 new tokens on a fixed neutral prompt). Full data:
`experiments/z041-coding-finetune/bench/cpu-bench.json`.

| metric | original | merged |
|---|---|---|
| model load (mean of 3) | 0.83 s | 0.86 s |
| tokens/s (mean of 3) | 6.95 | 6.95 |
| peak RSS (max of 3) | 3,309.6 MiB | 3,308.8 MiB |
| parameters | 494,032,768 | 494,032,768 |

The merged checkpoint is performance-identical to the original (same
architecture, same parameter count, no adapter at runtime).

## 7. Controls and integrity

- Restricted tier: 15/15 trusted oracle controls validated BEFORE any
  candidate was scored (`eval/restricted-tier-controls.json`).
- Repo unit suite: 221 passed, 10 skipped (Docker-conditional), 17 subtests
  passed — unchanged from Session 040.
- Holdout: sealed all session (loader refusal verified; seal untouched;
  nothing holdout-adjacent entered prompts, training data, or reports).
- Main and every other branch untouched; all work on
  `exp/zai-041-coding-finetune` only (see `BRANCH_ACTIONS.md`).
- Model-generated code executed ONLY inside the restricted execution tier
  (the project's Docker-isolation equivalent for this sandbox, per the
  documented `ARCHAGENT_LOCAL_EVAL=1` precedent; Docker argv parity
  preserved in `archagent/s040/exec.py`).
- One deviation found and fixed DURING the session (disclosed): the first
  merged-checkpoint save let transformers re-serialize tokenizer/config
  files (byte drift + a pre-tokenizer regex warning). Fixed by verbatim
  copies; the merged evaluation was re-run from scratch on the fixed
  checkpoint (results identical across the re-runs — recorded above).

## 8. What was NOT done

- No Stage-2 (contrastive/DPO) run — the 040 proposal gates it on authored
  chosen responses under the 033 allowlist and separate authorization.
- No hyperparameter iteration: one run, budget-capped, reported as-is.
- No GPU rental, no cloud compute, no billable resources (per instruction).
- No holdout evaluation: per the user's instruction, the original,
  weight-edited and fine-tuned models will be evaluated together on the
  sealed 24-task holdout once both modified checkpoints are frozen — this
  session froze the fine-tuned checkpoint for exactly that ceremony.

## 9. Artifacts

- `archagent/z041/` — dataset builder, dtype probe, trainer, merge+verify,
  paired eval driver, CPU benchmark (all importable, seeded, documented)
- `experiments/z041-coding-finetune/dataset/` — `sft-25.jsonl` +
  `dataset-stats.json` (sha-chained, contamination-scan table)
- `experiments/z041-coding-finetune/train/` — adapter (committed),
  `train-config.json`, `train-log.jsonl` (37 steps), `train-summary.json`,
  `dtype-probe.json`
- `experiments/z041-coding-finetune/merged-checkpoint/` — the merged
  bf16 checkpoint + `merge-manifest.json` (every sha256; on-disk, gitignored
  per convention; reproducible from the committed adapter + frozen base)
- `experiments/z041-coding-finetune/eval/` — tier controls + 24 paired
  evidence records (base/merged × A/B × 6 dev tasks) + summaries
- `experiments/z041-coding-finetune/bench/cpu-bench.json`

*Every number above traces to an archived artifact on this branch; nothing
is simulated, extrapolated, or rounded favorably. The 25-example pilot
cannot support broad generalization claims — the honest summary is:
pipeline proven end-to-end, one verified cross-domain family gain, crash
rate halved, dominant failure mode reduced but unresolved, pre-declared
success criteria not met.*
