# SESSION038A — Phase 3: PROPOSED fine-tuning plans (NOT executed)

**Nothing in this document was run.** No gradients, no training loops,
no adapters, no weight edits. AGENTS.md prohibits training on this
branch; these are designs for a **separately authorized** branch, with
data volumes, feasibility and costs measured from this session's
verified artifacts.

## Data inventory (from Phase 1 verification)

| Corpus | Examples | Distinct structures | Task families | Mean sample length |
| --- | ---: | ---: | ---: | --- |
| Model-origin SFT (independently verified) | 22 | 12 | 7 | ≤ 600 tokens (prompt ≈ 250 + candidate ≈ 50–300) |
| Teacher-origin SFT (distillation) | 3 pure teacher + 1 hybrid (labeled) | 4 | routes ×2, page ×1, invariant ×1 | ≤ 900 tokens |
| Preference pairs (same prompt) | **0** | — | — | — |
| Preference pairs (cross prompt, weaker) | 5 tasks / 21 rejected outputs | — | — | — |

Deduplication: the 22 model-origin examples collapse to 12 normalized
structures (60–46% duplication depending on counting level); 10 of 22
are the parent-side one-to-many pattern. **Family-weighted sampling is
mandatory** or the parent pattern is over-weighted ~10×.

Known gaps in the verified data: zero route handlers, zero type
interfaces, zero hooks/components/pages, zero multi-relation children,
no cascade semantics (the `rel-cascade` spec never asked for
`onDelete: Cascade` — documented curriculum defect).

## Plan 1 — LoRA pilot on model-origin verified examples

- **Goal:** pipeline validation, NOT a capability claim. 22 examples
  cannot teach generalization; the pilot's success criterion is
  "training runs, adapter loads, no regression on dev benchmark".
- **Method:** HF PEFT LoRA, r=16, α=32, dropout 0.05, target modules
  `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj`; bf16
  model + fp32 LoRA; max_seq_len 1024; lr 1e-4 cosine; 20 epochs
  (≈440 steps); seed pinned; prompt template = the exact archived
  prompts (prompt_sha256-verified); loss on candidate tokens only.
- **Feasibility on this 2-CPU/3-4-GiB box:** model bf16 ≈ 1.0 GiB +
  LoRA/optimizer ≈ 50 MiB + activations ≈ 0.5 GiB → ~2 GiB peak,
  fits. Step time ≈ 1–3 s → 15–45 min total. **CPU-feasible.**
- **Variants:** (a) base Qwen untouched; (b) SFT-model (these 22);
  (c) SFT + controller (same z038a retest harness) to separate
  parameter gain from system gain.
- **Cost:** $0 on this box.
- **Risk:** over-fitting 22 samples; report train loss AND dev
  benchmark, never loss alone.

## Plan 2 — teacher-distillation corpus (explicitly separate)

- **Corpus:** the 3 pure-teacher challenge pieces (GET search route,
  POST multi-branch route, page) + optionally the hybrid invariant
  (labeled `model-expression+teacher`). Provenance labels follow the
  037 `attribution.json` taxonomy; **never blended** with model-origin
  SFT in reporting.
- **Purpose:** the teacher examples cover exactly the families the
  model never solved (GET search-filter, POST validation) — the
  highest-value distillation targets.
- **Method:** identical LoRA config to Plan 1, separate adapter, label
  `SFT-distilled`.
- **Scale problem:** 3–4 examples is a symbolic pilot. A real
  distillation run needs ~50–200 teacher-written pieces across fresh
  domains (est. 2–4 h of authoring with verification) — propose only
  after Plan 1 validates the pipeline.
- **Cost:** $0 compute; authoring time is the real cost.

## Plan 3 — preference pairs (requires a collection run FIRST)

- **Blocker (measured this session):** the archives contain **zero**
  same-prompt (chosen, rejected) pairs — every verified candidate was
  accepted at its exact prompt with no rejected sibling. Only 5
  cross-prompt pairable tasks exist (21 rejected outputs), which is
  methodologically weak for DPO.
- **Required pre-step:** a dedicated sampling run — for each of ~30
  frozen spec pieces, sample K=8 completions at temperature on the
  IDENTICAL prompt, verify each with the Phase-1 replay stack
  (structural + prisma validate/push + SQLite behavior + seeded
  probes), then pair verified-correct vs verified-incorrect outputs.
  Estimated yield at 037-era solve rates (≈30–50% on these families):
  ~15–20 pairable tasks, ~60–120 pairs.
- **Method:** DPO, β=0.1, same LoRA targets; separate adapter;
  report win-rate on dev benchmark with the same seeds/protocol as
  the z038a retest.
- **Feasibility:** collection ≈ 30 tasks × 8 samples × ~25 s ≈ 1.7 h
  on this box; DPO on ≤200 pairs ≈ <1 h CPU. **Feasible locally.**

## Holdout policy (pre-registered)

1. `z038a` suite (orchard/marina/bakery, sha `ffff91b5…`) is now the
   **development benchmark** — its B (9/15) and R (8/15) baselines are
   recorded with seeds and budgets; adapter selection may use it.
2. A **new domain-disjoint holdout** (≥3 fresh domains, ≥15 pieces,
   same freeze discipline: spec+cases+oracles hashed before any
   training-adjacent run) must be frozen BEFORE hyperparameter
   selection for any trained variant.
3. No holdout task, spec sentence, demo, or probe case may appear in
   any training prompt, retrieval context, or principle store.
4. Evaluation of trained variants runs the exact z038a retest
   protocol (same seeds, budgets, probe strictness: no-verdict ≠
   pass) plus the new holdout, reporting paired per-family deltas.

## Go/no-go recommendation

**Conditional GO for Plan 1 (LoRA pipeline pilot) only**, because:
- the verification pipeline is proven end-to-end (22/22 replay);
- the data is model-origin, hash-chained, and family-labeled;
- CPU feasibility is measured (~2 GiB, <1 h).

**NO-GO for capability claims** from 22 examples; **NO-GO for DPO**
until the same-prompt collection run exists; **teacher distillation
only after** the Plan-1 pilot demonstrates the adapter workflow.
Any GPU rental (not needed for Plan 1) requires separate budget
approval.
