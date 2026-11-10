# Z.ai handoff — Session 039B: real isolated behavioral execution

**For:** Z.ai continuation agent, following completed Session 038A.

**Repository:** `7clan/ai-wieght-optimiization`.

**Read-only starting point:** the latest remote tip of `exp/qwen-generalization-learning-039`; verify that it includes this handoff. The last pre-handoff commit was `efef889687d82128486925bd6f0b770bc581aad4`.

**New work branch to create:** `exp/zai-039-docker-execution` (never reuse or modify another agent's active branch).

**Model:** base `Qwen/Qwen2.5-Coder-0.5B`, safetensors SHA-256 `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`.

## Mission

Resume from the existing frozen task and scenario artifacts; **do not
rebuild Session 038A or regenerate the 96 contracts**. Make real behavior
execution possible for model-generated TypeScript, GET/POST APIs, React,
and a full-stack vertical slice under the repo's required Docker sandbox.
Generate original Qwen code only after the verifier passes positive and
negative control tests. Preserve all provenance and failure evidence.

## Hard boundaries

- Read root `AGENTS.md`, `docs/SESSION039_GENERALIZATION_LEARNING.md`,
  and `docs/SESSION039_EXECUTION_BOUNDARY.md` completely before acting.
- Root policy forbids gradients, optimizers, LoRA, parameter updates, and
  training loops. This is **evaluation and data collection only**.
- Never execute model-generated Python/JavaScript/TypeScript on the host.
  `unshare -Urn` was the openly disclosed Session-038A compromise, but
  the **current Phase 039 executable runner requires Docker**. If Docker
  remains unavailable, stop execution and report it; do not weaken or
  bypass this requirement. A reviewed GitHub Actions Docker job is a
  potential path, but request approval before starting any job that may
  consume metered CI resources.
- Use restricted Docker: network none, read-only root and mounts,
  non-root, dropped caps, no-new-privileges, limited CPUs/RAM/PIDs/time,
  pinned images. Do not give candidate code access to repo credentials.
- Keep base model weights and `main` unchanged. Preserve all prior
  `exp/zai-*`, `exp/qwen-*` branches. No force pushes, branch cleanup or
  merges. Do not commit credentials or model checkpoints.
- Treat failed/missing/ambiguous verdicts as **no pass**, never as success.
  The strict tri-state and double-verdict bug lessons of 038A apply.

## Confirmed starting evidence

- 038A replay: 22/22 locally verified claims under disclosed `unshare`,
  **not Docker-reproduced**, 12 normalized structures, 7 families,
  zero API/UI examples, zero training-approved examples.
- 038A fresh suite: fixed baseline **9/15** vs repaired engine **8/15**;
  backend API routes remain the major gap (**1/12** total), with
  demo-vocabulary copying and optional-FK near-misses.
- 039 preparation: 96 authored, frozen **v2** contracts (54 train,
  18 dev, 24 holdout), v2 train/dev behavioral scenario plans, a
  `docker_only.py` wrapper and *state-transition only* trusted runner.
- Local preparation unit tests: 35/35 pass with mocked Docker calls.
  **No actual Docker candidate execution or model learning has happened.**

## Step-by-step work order

### Phase 0 — recover and verify without spending model tokens

1. Create a fresh worktree/branch from the exact 039 starting point.
   Inspect `git status`, existing processes and model-cache hashes.
   Preserve unrelated StockPilot files and Z.ai worktrees if present.
2. Reproduce the standard-library preparation tests and frozen SHA
   checks:

   ```bash
   python -m unittest tests.test_finetune_audit tests.test_candidate_queue \
     tests.test_proof_gate tests.test_s039_preparation -v
   python -m archagent.s039.curriculum --check
   python -m archagent.s039.curriculum_v2 --check
   python -m archagent.s039.scenarios --suite-version 2 --split train --check
   python -m archagent.s039.scenarios --suite-version 2 --split dev --check
   python -m archagent.finetune.reconcile_038a --repo . \
     --out experiments/z039-generalization-learning/replay-reconciliation.json
   ```

3. Check `command -v docker` and `docker info` **without executing any
   generated code**. If unsupported, stop the live phase; propose a
   compliant Docker-capable runner or a manually triggered GitHub
   Actions workflow. Never silently substitute host Node/Bun.

### Phase 1 — prove the verifier works, then permit Qwen candidate tests

1. Supply a vetted Node 24 image pinned by immutable digest (do not use
   `node:latest`) and exercise `archagent.s039.invariant_eval` in Docker.
   Its candidate path is
   `experiments/z039-generalization-learning/candidates/<task-id-with-__>/output.ts`.
2. Run a clearly labeled **trusted positive control** that implements
   the state-transition spec and a separate **known-bad control** that
   copies the demo's stage vocabulary. The first must pass and the
   second must fail on the exact domain states. This is validation of
   the oracle, **not evidence that Qwen solved the task**.
3. Exercise boundary/security failures: no image digest, no Docker,
   timeout, invalid TypeScript, missing export, duplicate result
   markers, input dir escape, partial check failure. Fix the harness
   before scoring any model output. Preserve logs of all corrections.
4. Implement **GET and POST route** evaluation against a fresh Prisma
   SQLite fixture. Check actual HTTP statuses, empty and filtered list
   envelopes, ordering, FK absence/nullability, numeric limits,
   duplicate conflict, and absence of writes on 400/404/409.
5. Implement React interaction checks and one end-to-end form→API→DB→UI
   case. All browser activity involving untrusted UI must remain inside
   the restricted runtime; screenshots should show actual rendering,
   not generated decorative mockups. Separate teacher scaffolding from
   Qwen bytes in attribution.

### Phase 2 — bounded model-generated curriculum collection

1. Begin with **two train and two dev contracts** across distinct
   families (one invariant, one GET/POST). Compare the model's exact
   output bytes to the archived generation logs and run each in Docker.
   No teacher-written target solutions in model prompts.
2. Expand only after behavior tests and control probes are reliable.
   Prioritize GET search/order and POST validation because 038A had
   near-zero success there. Sample under a fixed token/attempt budget,
   record all failures, use test feedback only from the declared public
   cases and never from sealed holdout cases.
3. Save each prompt hash, candidate hash, model checkpoint hash, seed,
   output tokens, elapsed time, origin classification, source path,
   sandbox properties, exact behavioral cases and result summary.
4. Deduplicate by task family and structural fingerprint. A correct
   repeated FK schema in a ninth vocabulary is not a ninth independent
   programming skill. Teacher rewrites must be labeled separately and
   never counted as model-origin successes.

### Phase 3 — independent reporting (still no training)

1. Publish task-level **base single-shot pass@1** and **controller
   solve@N** as distinct metrics with the same frozen task IDs.
   Report attempts/tokens/CPU/RAM, artifact hashes and behavior passes.
2. Use the 18 development tasks for controller selection. Keep all
   24 v2 holdout tasks closed until every model selection, budget and
   prompt is frozen; freeze predictions BEFORE exposing final cases.
3. Compare new outcomes to Session 038A cautiously: different domains
   and suite sizes are not direct paired benchmarks. If no improvement,
   say so plainly and preserve negative evidence.
4. Produce `docs/ZAI_SESSION039_DOCKER_EXECUTION.md` and a sanitized
   machine-readable report under `experiments/z039-zai-execution/`.
   Push checkpoints to **your own branch** after each verified phase,
   keeping `main` and all other branches untouched.

## Required final response

Report exact GitHub branch/commit; Docker image digest and **actual**
isolation (or reason blocked); positive/negative control outcomes;
number of Qwen candidates run; behavior pass counts per API/schema/
invariant/UI/integration family; base vs controller denominators;
RAM/CPU/time/tokens; model-written vs teacher-written byte accounting;
known test-harness defects, limitations and whether the v2 holdout
was ever opened. Do not claim training or improved model weights.

**Stop condition:** if generated-code execution cannot run in a
compliant Docker-capable environment, complete the static preparation,
publish an honest blocked report and request a user-provided compliant
environment or permission to use metered CI. Do not work around the
isolation boundary.
