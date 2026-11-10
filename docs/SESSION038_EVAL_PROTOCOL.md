# Session 038: proposed frozen evaluation and fine-tuning controls

**Status: a pre-registration proposal, not a training run.** The existing
root `AGENTS.md` forbids gradients, optimizers, backpropagation, LoRA and
training loops. Nothing in this plan overrides that instruction.

## Research question

Can verified, model-generated examples improve the *base*
`Qwen/Qwen2.5-Coder-0.5B` on genuinely unseen full-stack contracts **after
controlling for the benefit of the scaffold, execution feedback and retries**?

Session 037's fixed baseline (9/15) surpassed the adaptive system (6/15),
despite relation-family progress. Consequently the first step is to improve
independent reliability measurements, not assert that the model learned.

## Freeze these choices before measuring

1. **Checkpoint identity.** Use the same base checkpoint as Sessions 036–037;
   verify its reported exact SHA-256 `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`
   against the actual local checkpoint manifest before trusting it. Do not
   substitute the Instruct checkpoint.
2. **Holdout.** Author entirely new project families and frozen hidden
   behavioral tests before experimenting. Split by application/problem
   family, not individual generated files or near-duplicate prompts.
   Exclude overlapping session curricula, code snippets and reference
   solutions from retrieval or model selection.
3. **Metrics.** Report no-feedback one-sample pass@1 separately from
   feedback-guided solve rates. Specify exact sample counts, random seeds,
   decoding parameters and token caps. Compare identical tasks with the same
   source and test harness under all tracks.
4. **Execution.** Run every generated Python, JS or TS candidate only inside
   an approved isolated Docker worker. Collect CPU-time, elapsed time, peak
   RSS, generated tokens, retries, and any timeouts. Keep visible tests
   distinct from untouched hidden tests.
5. **Attribution.** Archive unmodified model outputs with prompt/seed/model
   hashes. Track teacher-written bytes and deterministic scaffold bytes
   separately. A full-stack product that depends on trusted integrations is
   a model-assisted product, not a model-only app.

## Mandatory comparison matrix

| Track | Frozen checkpoint | Fine-tuning | Generation controller | What it isolates |
| --- | --- | --- | --- | --- |
| A | Untouched base | None | None | Native pass@1 |
| B | Untouched base | None | Same fixed staged controller | System uplift |
| C | Base + verified model-origin adapter | Proposed, permission-gated | None | Parameter uplift |
| D | Same adapter as C | Proposed, permission-gated | **Identical** controller from B | Interaction of training and system |

Only after separate disclosure may a fifth arm use verified teacher-origin
distillation. Do not mix it into C/D or count teacher code as Qwen-written.
If C/D are not authorized or not feasible on current hardware, report A/B
with C/D as **not run**, rather than substituting a different measurement.

## Primary and secondary endpoints

Primary endpoint: **functional correctness on independent holdout contracts**
(all required API paths, schema relationships, state invariants and UI flows
pass). Publish raw per-task pass/fail IDs and the exact denominator.

Secondary endpoints:

- Syntax/schema/typecheck pass rates reported separately from behavior.
- Pass@1 (single generation) versus guided solve@N (with extra inference).
- Resource cost: total wall time, generated tokens per solved contract,
  peak RAM, CPU usage, failed attempts and Docker timeouts.
- Critical regressions: security boundaries, bad-input behavior, data
  integrity, inaccessible mobile controls and unrelated programming tasks.
- Robustness: independent seeds, a genuinely different domain, and a
  negative-control task where shallow template copying should fail.

Avoid making a statistical generalization claim from a 15-contract suite.
Report uncertainty and expand independent tasks if the apparent gain is
small. Never choose prompts or adapter checkpoints based on final holdout
outcomes.

## Candidate dataset qualification

Current archive audit: 571 prompt/candidate records, 22 unique traceable
in-loop acceptances queued for replay, **zero independently verified
training examples**. No raw training set has been exported.

Before any dataset export:

1. Verify source hashes and ownership/license of all examples.
2. Replay in a sandbox with independent behavioral tests; retain negative
   cases, not just test-passing outputs.
3. Human-review accepted examples and their exact provenance, marking
   generated, teacher-edited, or authored as disjoint classes.
4. Deduplicate by task family, normalized code and output hashes.
5. Freeze train/development/holdout splits **before** any tuning and
   record content digests for auditing.
6. Exclude any examples whose test oracle was corrected after the answer
   was inspected or whose results came from a contaminated run.

Only after explicit training authorization and a hardware feasibility test:

- Use a narrowly scoped PEFT LoRA pilot with adapter saved apart from the
  unchanged base. Pin versions, tokenizer, prompt/completion formatting,
  rank, alpha, target modules, optimizer, seed and evaluation cadence.
- Measure actual RAM/GPU memory; do not imply the existing 2-CPU/4-GiB
  machine can perform the pilot or buy/rent computing without permission.
- Stop early on divergence, data leakage, resource overruns, or unrelated
  benchmark regression.

## Interpretation rules

- A better training loss is not evidence of better autonomous coding.
- Improved B but not C means the scaffolding made the difference.
- Improved C on *new* tasks is evidence consistent with parameter-level
  generalization, contingent on replication and negative controls.
- D may outperform C because of controller assistance; report those gains
  separately, not as independent model capability.

## Primary implementation and research references

- [Qwen2.5-Coder-0.5B base model card](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B)
- [Hugging Face TRL: SFTTrainer reference](https://huggingface.co/docs/trl/sft_trainer)
- [Hugging Face PEFT: LoRA configuration reference](https://huggingface.co/docs/peft/main/package_reference/lora)
- [QLoRA research paper](https://arxiv.org/abs/2305.14314)
- [Repository Session 037 report](ZAI_GENERALIZATION_ENGINE_037.md)
- [Repository execution and training rules](../AGENTS.md)

**No training, merging into `main`, branch deletion, or Z.ai branch edit
is authorized by this file.**
