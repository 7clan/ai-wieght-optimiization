# Session 038 — Fine-tuning readiness, not training

**Branch:** `exp/qwen-finetune-readiness-038`  
**Base:** Session 037 `f0b541f09c8d5c6a329262cd41b02b0fa378bece`  
**Model:** `Qwen/Qwen2.5-Coder-0.5B`, unchanged  
**Status:** Data audit and experiment design only. **No model weights or adapters were trained.**

## Why there is a separate preparation phase

The repository's root `AGENTS.md` explicitly prohibits gradients,
backpropagation, training loops, optimizers, and LoRA in new experiments.
The user's interest in a *later* fine-tuning experiment does not replace
that restriction automatically. Actual training should occur on a new,
explicitly authorized branch with revised scoped instructions and a
hardware/cost plan approved by the user.

The historic evidence also makes premature training risky:

| Experiment | Fixed baseline | Adaptive system | Conclusion |
| --- | --- | --- | --- |
| Session 036 | 7/12 | 4/12 | Policy regressed on an unseen full-stack task |
| Session 037 | 9/15 | 6/15 | Engine improved relations and token efficiency, but lost invariants |

Neither result proves a generalizable improvement in the model itself.
Session 037's corrected evaluator exposed previously hidden route-probe
failures and cross-track contamination. Consequently, training from all
"accepted" samples would teach unverified code and could amplify defects.

## Archived data audit (read-only)

Reproduce:

```bash
python -m unittest tests.test_finetune_audit -v
python -m archagent.finetune.audit_archives --repo . \
  --out experiments/finetune-readiness-038/archive-audit.json
```

The audit scanned archived generation JSON files, without executing their
code, exporting raw prompts, or printing possible secrets:

| Finding | Count |
| --- | ---: |
| JSON files examined in generation directories | 903 |
| Records containing string `prompt` and `candidate` | **571** |
| Other JSON files missing that pair | 332 |
| Additional repeated candidate hashes | 209 |
| Additional repeated prompt hashes | 367 |
| Blank candidates | 1 |
| Candidates with obvious placeholder/echo markers | 46 |
| Candidate records actually approved for training | **0** |

The duplicate and marker counts are screening signals, not correctness
measurements. Markers can produce false positives; examples without markers
can still be wrong. Candidate hashes are deliberately recorded only in
aggregate, not as a publishable code dataset. The audit does not attempt
to certify attribution or behavior from archive metadata.

Session 036 contributes 147 parsed records; Session 037 contributes
424. The archives include exploratory, failed, repeated, and amended
experiments, so these are *not* 571 independent tasks.

## Data-qualification gate

Before producing any trainable dataset:

1. Reconstruct candidate provenance from each original generation and
   ledger, with exact checkpoint, prompt, seed, and output hash. Exclude
   all teacher-written code from the strictly model-generated dataset.
2. Re-run syntax, schema/type checking, and **independent behavioral
   checks** inside the approved, network-disabled execution sandbox.
   A passing AST or source-string gate alone is insufficient.
3. Deduplicate by output, normalized AST, and problem family. Group
   related examples in the same split; never split variants of one task
   between train and test.
4. Remove secrets, private text, harness instructions, prompt-echo,
   truncated samples, examples with evaluator uncertainty, and any
   examples whose ground truth changed after their predictions were seen.
5. Separate **model-origin SFT**, **verified teacher-distillation SFT**,
   and **preference pairs** into explicitly labeled corpora. Never
   blend their provenance when reporting training effects.
6. Freeze a genuinely new, domain-disjoint post-training evaluation suite
   and its scoring rules before choosing hyperparameters. Keep it outside
   both training and development inputs, including retrieval contexts.
7. Publish a dataset card with sources, exclusions, licenses, task-family
   counts, positive/negative balance, hashes, and contamination audit.

Only verified, appropriately licensed training examples can graduate
from `QUARANTINED` to `ELIGIBLE`. This script does **not** perform that
graduation; doing so requires actual independent execution and review.

### First provenance reconstruction checkpoint

The next script joins Session-037 generation records to their
per-attempt acceptance ledgers, checking piece ID, seed, SHA-256 output
fingerprint, in-loop gate, duplicate outputs, and known contaminated
run exclusions:

```bash
python -m unittest tests.test_finetune_audit tests.test_candidate_queue -v
python -m archagent.finetune.candidate_queue --repo . \
  --out experiments/finetune-readiness-038/candidate-queue.jsonl \
  --summary experiments/finetune-readiness-038/queue-summary.json
```

- Reported in-loop acceptances: **30**.
- Additional duplicate outputs skipped: **8**.
- Traceable unique outputs awaiting independent replay: **22**.
- Known contaminated ledgers excluded: **2**.
- Independently behavior-verified training examples: **0**.

This is a queue of promising *references*, not a dataset. A structural
gate and an archive ledger may both be wrong. The preparation workspace
does not provide Docker, so no archived model-generated code was run
here. The next isolated evaluation task is documented in
[`SESSION038_ZAI_HANDOFF.md`](SESSION038_ZAI_HANDOFF.md).

## Proposed staged experiment after permission is granted

### Stage A — independent benchmark before training

First compare Session 037's fixed ladder and improved controller on
fresh, domain-disjoint tasks with corrected generation caps and fixed
route probes. This is a *new* benchmark, not retroactive rescoring of
the frozen Session 037 suite. Publish both accuracy and tokens per
correct contract and preserve failed examples. If system-level gains
disappear, record that result before investing in parameter tuning.

### Stage B — small parameter-efficient pilot

After the data gate and explicit authorization, consider the official
Hugging Face PEFT LoRA workflow on a bounded set of verified examples.
QLoRA is an alternative if a suitable GPU is available. Pin the model,
tokenizer, dependency versions, seed, rank, target modules, and prompt
template. Never assume the existing 2-CPU/4-GiB box has enough training
headroom; measure feasibility rather than silently using more resources.
Any paid GPU rental requires separate budget approval.

Use at least these variants:

- **Base:** untouched Qwen, same prompt and decoding.
- **SFT-model:** model-origin examples only, no teacher outputs.
- **SFT-distilled:** optional, separately labeled teacher solutions.
- **Adapter + controller:** the best training variant with the same
  Session 037 harness (distinguishes parameter gain from system gain).

Always save adapters separately and preserve the base checkpoint.
Only consider merging an adapter after evaluation and memory checks.

### Stage C — independent generalization test

Score on fresh domains with the same hardware and decoding configuration:

- Pass@1 functional correctness and syntax validity separately.
- Behavioral property checks, schema integrity, and API status cases.
- Token use, time, peak RAM, and retry counts.
- Regressions on unrelated programming tasks.
- Transfer under **both** no-controller and same-controller conditions.

Do not call improved training loss "learning to program better" unless
independent execution success improves. A small positive result on one
task family is not evidence of general senior-developer competence.

## Research and implementation references

- [Hugging Face — parameter-efficient fine-tuning](https://huggingface.co/docs/transformers/peft)
- [QLoRA paper](https://arxiv.org/abs/2305.14314)
- [Qwen2.5-Coder-0.5B-Instruct model card](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct)
- [Session 037 experimental report](ZAI_GENERALIZATION_ENGINE_037.md)
- [Repository AGENTS instructions](../AGENTS.md)

## Stop conditions

- Do not run gradient training or edit `AGENTS.md` in this readiness branch.
- Do not mix future holdouts into any training, prompt evolution, or
  retrieval corpus.
- Do not download or rent hardware requiring cost without permission.
- Do not execute archived model-generated code outside the approved sandbox.
- Do not edit Z.ai's branches, merge into `main`, or force-push.

**Decision required:** Explicitly authorize a separate training branch
after the independent benchmark and data qualification are complete.
