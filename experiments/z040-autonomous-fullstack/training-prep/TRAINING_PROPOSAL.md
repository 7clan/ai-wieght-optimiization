# SESSION040 Training Proposal — prepared, NOT executed

**Authorization status:** training is FORBIDDEN in this session and nothing
below was run. This document is the Phase-8 deliverable: a frozen
specification a future, separately-authorized session could execute or
amend.

## 1. Objective (from the Phase-7 evidence)

The binding constraint on the frozen Qwen2.5-Coder-0.5B is **in-context
example dominance**: 11/17 contract-first failures copy the demo's domain
nouns instead of binding the task's own nouns (vocabulary-correct failures
are 5/17; crashes 5/17). Prompt-side assistance is saturated (A 0/18,
B 1/18, C 1/18 with 0/17 feedback conversions, D 0/6 on v2). The training
objective is therefore:

1. **Primary:** task-noun binding — given a prompt containing an example in
   domain X and a task in domain Y, produce Y's nouns (measured by the
   vocabulary-lock counter: zero demo-domain nouns in output).
2. **Secondary:** route/manager generation shape — complete multi-branch
   handlers (400/404/409/201) without execution crashes (measured by
   EXECUTION_FAILED rate).

## 2. Method (proposal)

- **LoRA** on the frozen base (`aff8914e…a47f80`), per the 038A Plan-1
  pilot design: rank 16, alpha 32, target modules q/k/v/o + MLP down/up,
  fp32 accumulation, lr 1e-4 to 2e-4 cosine, 3 epochs, batch 8 effective.
- **Stage 1 (SFT):** the 25 verified model-origin candidates (038A's 22 +
  040's 3), prompt-formatted exactly as their archived prompts
  (contract-first Track-B template), completion = the verified candidate
  bytes, loss on completion tokens only.
- **Stage 2 (optional, after Stage-1 eval):** contrastive/DPO on
  task-noun binding using the 6 `contrastive-pairs-040.jsonl` leads plus
  new pairs authored under the 033 allowlist (chosen = verified pass or
  teacher-authored ONLY if governance approves; rejected = archived
  demo-vocab failure). Rejected-side loss weight 0.1–0.5 sweep.
- **Guardrails:** no training on dev/holdout material (enforced by split
  filter at data-build time, hash-chained); the model pin is re-verified
  before and after; all adapters sha256-archived.

## 3. Data plan

- Source of truth: archived evidence records (prompt + verified candidate,
  sha256-chained). No new generations needed for Stage 1.
- Stage 2 requires authoring chosen responses for the 6 lead prompts
  (allowlist-compliant: the model's own verified bytes from another
  attempt, or abstract pattern text — NOT teacher code unless governance
  relaxes the 033 rule for the chosen side of preference pairs; the
  rejected side is always archived model output).
- Dedup: by (prompt sha, candidate sha) pairs; suite-version tagged.

## 4. Resource requirements (honest)

This sandbox (2 CPU, 4 GB RAM, no GPU) **cannot train** — even the 0.5B
LoRA needs ~8 GB VRAM-class hardware or many CPU-hours beyond the
interactive budget. Training must run in an authorized environment
(GitHub Actions GPU runner or user-provided hardware), with the dataset
exported from this repository (everything needed is on-branch).

## 5. Frozen evaluation plan (must be run unmodified after any training)

1. **Seal ceremony:** predictions + this plan are committed; only then may
   the 24 holdout tasks be unsealed for evaluation.
2. **Primary endpoints (dev split, radiostation, v2):** Track-A single-shot
   pass@1 (the model-only metric — this is the number that must move);
   Track-B pass@1; vocabulary-lock violations per candidate (demo-noun
   count = 0 target); EXECUTION_FAILED rate.
3. **Secondary endpoints:** Track-C first-repair conversion rate (baseline
   0/17); the app-level suites re-run with the adapter (API 25/25,
   invariant 7/7, browser suite) on a fresh GearHut-style spec NOT used in
   training (a new frozen app spec, domain disjoint from gearhut and all
   curriculum domains).
4. **Controls:** untrained-base re-run in the same harness on the same
   seeds (paired); the 15 restricted-tier controls re-validated; the
   adversarial spoof suite 30/30; unit suite green.
5. **Success criteria (pre-declared):** Stage-1 success = Track-A dev
   pass@1 ≥ 2/6 with vocabulary-lock violations = 0 on ≥ 5/6 candidates and
   no regression on the 038A-verified families. Failure to meet criteria
   with the adapter is reported as-is.
6. **Reporting:** per-track tables in the SESSION040 format, paired
   base-vs-adapter, all evidence archived with tier labels.

## 6. What this session already froze for that future run

- The evaluators (6 families), the restricted tier, the controls, the
  track protocol and the app-level suites — all on-branch and validated.
- The failure taxonomy and cost baselines (tokens/wall per track).
- The dataset card, candidate queue and contrastive leads (this directory).

*No training, no gradient, no adapter was produced by SESSION040.*
