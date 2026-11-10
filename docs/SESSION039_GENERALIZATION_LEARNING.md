# Session 039 — generalization-learning preparation (no training)

**Branch:** `exp/qwen-generalization-learning-039`  
**Base:** Z.ai's completed Session 038A (`8501fc3f8711bc042ed6d70be659f726a8f2ac93`)  
**Model:** frozen `Qwen/Qwen2.5-Coder-0.5B`  
**Status:** Phase 0 evidence reconciliation + Phase 1 authored curriculum **complete**;
Phase 2 scenario plans prepared, execution harness pending. No inference or training run here.

## The research milestone

Find an actual parameter-level improvement on an unseen suite of full-stack
coding contracts, separating model capability from teacher-written code,
prewritten scaffolds, feedback search and harness corrections. The last
fresh suite did **not** show a system-level gain: baseline 9/15, revised
controller 8/15. API routes remain the principal weakness (only 1/12
successes across both tracks), alongside domain-vocabulary copying and
relation optionality.

## Phase 0 — Session 038A evidence reconciliation

```
python -m archagent.finetune.reconcile_038a --repo . \
  --out experiments/z039-generalization-learning/replay-reconciliation.json
```

The metadata checker independently compares Session 038A's queue, replay
ledger, candidate manifest, frozen generation-file hashes and reported
behavioral layers. It finds 22 internally consistent positive **claims**:
19 Prisma models and three invariants. It also confirms 12 distinct
normalized structures, only seven task families and zero explicitly
authorized training examples.

It is **not** independent re-execution. Z.ai reports `unshare -Urn`
user/network-namespace isolation because Docker was unavailable. Our
Session 038 proof gate requires Docker, so these results cannot silently
graduate to its Docker-reproduced tier. They remain useful, explicitly
labeled local replay evidence pending independent execution and review.

## Phase 1 — 96 frozen, domain-disjoint task specifications

The *contract-only* curriculum has six skill families per application:

1. Prisma relationship/required-vs-optional foreign key and deletion rules;
2. GET search/filter/order/include with correct empty-state envelope;
3. POST strict validation, FK lookup, duplicate check, persistence;
4. domain-specific state-transition invariant, including negative cases;
5. responsive, accessible React search/status UI with keyboard behavior;
6. integrated form→API→database→refreshed UI flow with error paths.

| Split | Domains | Contracts | Allowed use |
| --- | ---: | ---: | --- |
| Curriculum | 9 | **54** | Candidate generation and later training-data collection |
| Development | 3 | **18** | Controller comparisons / adapter selection (not training) |
| Sealed holdout | 4 | **24** | Final evaluation only, after all choices are frozen |
| **Total** | **16** | **96** | **Zero generated solutions so far** |

Each task requires positive and negative behavior cases. Splits are grouped
by entire application, so variants of the same task family in one domain
cannot straddle the train/holdout boundary. The hand-authored contracts
contain **no generated candidate source and no teacher solution**. They
are NOT 96 verified training examples or full working applications.

Freeze/check:

```
python -m archagent.s039.curriculum --check
python -m unittest tests.test_finetune_audit tests.test_candidate_queue \
  tests.test_proof_gate tests.test_s039_preparation -v
```

All suite bytes are recorded in
`experiments/z039-generalization-learning/suite/MANIFEST.json`. Its freeze
check refuses edits, and the freeze writer refuses to replace existing
files. The holdout suite SHA-256 is
`9a09d55b7c3eb8b140905fcef44c03b2ed0818b95adbb2f60a1094b0afc93e41`.

### Phase 2a: reproducible scenario plans (prepared, not executed)

`archagent/s039/scenarios.py` maps each train/dev contract to independent
fixture rows plus required positive and negative test cases. It covers
boundary values, missing/invalid foreign keys, duplicate writes, case
insensitive and combined search filters, valid/invalid state transitions,
keyboard/mobile interaction and persistence across UI refresh.

```
python -m archagent.s039.scenarios --split train --check
python -m archagent.s039.scenarios --split dev --check
```

Output files:

- `experiments/z039-generalization-learning/scenarios/train.json` — 54
  tasks with unexecuted behavior scenarios.
- `experiments/z039-generalization-learning/scenarios/dev.json` — 18
  tasks with unexecuted behavior scenarios.

The builder expressly refuses to load or export holdout scenarios before
final scoring. No generated code has been run, so **0 behavior passes**
are claimed at this stage. The scenario specifications must themselves
be independently reviewed and run against known-good/known-bad controls
before an eventual grading outcome is trusted.

**Contract review note:** the v1 `schema-relationship` specification
includes a measurement field but does not explicitly require persisting
the state field later used by some UI fixtures. This is a potential
cross-module mismatch; it must be resolved with a **versioned new
suite**, with original v1 bytes kept intact, before asserting integrated
status-persistence results. Do not silently alter the frozen v1 contracts.

### Phase 2b checkpoint: status contract amended, Docker-only invariant path implemented

A **versioned v2 suite** now resolves the mismatch: the child Prisma
model stores `status` with the domain's initial state, GET exposes it,
POST creates it, and integration uses the persisted value. Original v1
specifications and scenario plans remain intact. The v2 plans are frozen
in `suite-v2/` and `scenarios-v2/` (train/dev only).

The first Docker-only execution path is implemented for state-transition
invariants with strict image digest requirement, restricted containers and
single-verdict result parsing. Its actual runtime compatibility and
behavioral correctness are **unverified** here because Docker is absent.
All other API, Prisma, React and full-stack execution paths are still to
be built. See [`SESSION039_EXECUTION_BOUNDARY.md`](SESSION039_EXECUTION_BOUNDARY.md).

## Phases 2–4 — not yet run

### Phase 2b: contract-to-behavior harness

- Implement *trusted* reference oracles and independent behavioral checks,
  with negative controls proving failures are detected. Prioritize GET and
  POST route cases that Session 038A found genuinely hard.
- Test every generated candidate only in an approved restricted execution
  environment. If Docker is unavailable, clearly label any alternative
  local-evaluation tier; **do not** silently count it as Docker-verified.
- Capture exact prompt/model/candidate digests, seeds, tokens, test-version
  digests, teacher bytes, and provenance without embedding secrets or
  private prompts in reports.
- Record near-miss counterexamples and derived general *patterns*, not
  only verbatim patches. Do not treat remembering a single fixed program
  as evidence of learning an unfamiliar problem.

### Phase 3: resource feasibility and permission gate

- Before proposing expensive training, measure a no-gradient model forward
  pass and a minimally scoped adapter feasibility benchmark under local
  RAM/CPU limits. Any actual gradient-based step is **not authorized** by
  the current `AGENTS.md`. A separate explicit approval and scoped rules
  change are required first.
- Session 038A's quoted `~2 GiB / <1 h` CPU LoRA feasibility is an
  untested estimate, not an actual training benchmark.
- Scrub sensitive source data; review example licenses and contamination;
  prevent task-domain and template leakage into the untouched holdout.

### Phase 4: optional authorized learning experiment

Compare the *same* frozen model and prompts across:

| Variant | Weights | Controller | Metric |
| --- | --- | --- | --- |
| A | base frozen | none | True one-sample model pass@1 |
| B | base frozen | fixed controller | System-level solve rate |
| C | base + independently verified adapter | none | Parameter-level change |
| D | same adapter | same controller as B | Interactions, extra compute |

Report original and repaired source attribution, end-to-end success,
API/React/schema sub-scores, CPU/RAM/latency, and per-task outcomes with
uncertainty. More solved tasks on an independent frozen test (without
extra inference) would be evidence **consistent with** learned transfer,
not proof of general senior-developer ability. Do not claim statistical
success from just one tiny domain.

## Findings and limitations of this checkpoint

**What is measured:** 22 replay claims agree with their archived hashes
and metadata; 96 authored contracts are byte-frozen; unit tests pass.

**What is not measured:** ability to write these contracts, correct API
or React behavior, full-stack integration, code generalization, any
training effect, or an actual memory/time bound for LoRA.

**Governance:** `main` and Z.ai's `exp/zai-*` branches remain untouched;
the exact 038A evidence remains preserved. No gradient work, LoRA,
unsandboxed candidate execution, force push, or model-weight change.

## Source references

- [Z.ai Session 038A evidence and negative findings](ZAI_SESSION038A_INDEPENDENT_RETEST.md)
- [Z.ai's separate proposal for pilot training](ZAI_SESSION038A_TRAINING_PLANS.md)
- [Our evidence consistency gate](../archagent/finetune/reconcile_038a.py)
- [Model's official base checkpoint](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B)
- [Official PEFT adapter guide](https://huggingface.co/docs/transformers/peft)
- [Repository's experiment restrictions](../AGENTS.md)
