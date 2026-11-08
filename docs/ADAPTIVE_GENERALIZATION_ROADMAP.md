# Qwen Adaptive Generalization Lab

**Branch:** `exp/qwen-adaptive-generalization`  
**Base:** `main` at the moment this branch was created.  
**Status:** Research plan and experimental workspace. No model training or model improvement has yet been performed on this branch.

## What we are trying to solve

Develop a **single, hardware-constrained Qwen2.5-Coder-0.5B coding agent** that can tackle *unseen* full-stack problems, understand failures, consult relevant documentation, test hypotheses, and make progressively better decisions. Repeating a stored answer to a familiar problem does **not** count as generalization.

The project has two distinct, complementary tracks. They must be measured independently.

### Track 1 — Transferable problem-solving controller (permitted now)

Keep the model weights frozen. Give the agent a reusable, low-memory procedure, not a giant cache of solved tasks:

1. **Interpret:** identify user goal, scope, functional acceptance criteria, and system constraints.
2. **Decompose:** specify frontend, backend, persistence, deployment, and security contracts before generation.
3. **Investigate:** for unknown APIs or errors, retrieve primary documentation, cite the exact source, and record an uncertainty/hypothesis. Do not claim external search if it was unavailable.
4. **Act:** generate one bounded patch at a time with file, line, and dependency awareness.
5. **Execute:** run reproducible static analysis, unit tests, API integration checks, and real browser interaction tests in a sandbox.
6. **Diagnose:** identify the smallest causal reason for a failure. Retry with a new hypothesis; stop loops that keep repeating the same unproductive action.
7. **Verify:** score behavior on new tasks and held-out variants, including actual API/DB persistence, security, accessibility, and independent visual assessment.
8. **Reflect at the strategy level:** summarize *transferable debugging principles* (e.g., isolate the failing component, inspect assumptions, verify dependencies), distinct from storing an exact answer; test whether the principles transfer to unrelated tasks.

An external controller can improve the **system's** capability without changing Qwen's intrinsic weights. All instructor/teacher-authored code must be marked and excluded from model-only capability claims.

### Track 2 — Optional lightweight parameter adaptation (NOT authorized by current AGENTS.md)

This is a **proposal only** until the user explicitly overrides the current repository prohibition on gradients, backpropagation, optimizers, training loops and LoRA for new experiments.

If separately authorized:

- Use *verified traces from diverse tasks* to teach reusable general coding/debugging patterns, not memorized solutions.
- Freeze a baseline, define task families and truly untouched held-out tasks **before** adapting.
- Bound compute, RAM and resulting inference footprint. Preserve original model weights; save separately versioned, reversible artifacts.
- Evaluate unassisted first-attempt correctness and tool efficiency, not just success after teacher repairs.
- Abort or roll back if transfer fails, unrelated capabilities regress, or the 2-CPU/~4-GB resource envelope is exceeded.
- No large teacher model or additional resident model is permitted at runtime just to hide a weak Qwen baseline.

Do not present a proposed training method as a measured gain.

## Four-way evaluation

| ID | Model | Controller | Answers |
| --- | --- | --- | --- |
| A | Unmodified 0.5B | No | How good is frozen Qwen alone? |
| B | Unmodified 0.5B | Yes | How much does the general problem-solving system help? |
| C | Adapted 0.5B (only if authorized) | No | Did the model **itself** learn transferable skills? |
| D | Adapted 0.5B (only if authorized) | Yes | Do intrinsic learning and the controller combine? |

Report separately: correct functionality, coverage of required features, backend/API and durable persistence, security failures, first-pass vs repaired code, teacher lines, inference tokens, calls, wall-clock, peak RAM, CPU usage, human interventions, aesthetic quality using independent raters, browser screenshots, and performance on **unseen** task families.

Never use the held-out test prompts to build the controller, select memory entries or adapt parameters. If a benchmark has been used in past experiments, label it **exploratory**, not held-out.

## First milestone

Create a reproducible benchmark that requires **three independently specified, nontrivial applications**:

1. Project dashboard with CRUD, search, filters, authentication where required, backend endpoints and stored state.
2. Document/record management tool with upload, access checks, search, deletion confirmation and backend storage.
3. A deliberately unrelated application introduced *after* the general controller is frozen.

For each: verify API/database functionality (not only React/localStorage), reload persistence, invalid inputs, mobile layouts, keyboard access, end-to-end workflows and unassisted vs assisted provenance. Publish **real browser screenshots**, never synthetic examples.

**Success criterion:** improvement on genuinely new problems at the same budget, with reproducible evidence. "The teacher built a working app" and "the model can now build one" are different claims.

## Operating boundaries

- **Hardware:** ~2 CPU cores, ~4 GB RAM; budget every experiment.
- **Model:** Qwen2.5-Coder-0.5B. Do not swap to a larger runtime model.
- **Weights:** preserve the frozen checkpoint. No training until separately authorized.
- **Safety:** run model-generated code only in resource-limited, network-disabled/unprivileged sandboxes. If sandbox unavailable, stop execution and report it.
- **Provenance:** tag each file or patch as Qwen original, Qwen with bounded teacher repair, teacher integration, or fixed scaffolding. Save raw prompts, seeds, decoding params, hashes, test outputs and screenshots where non-sensitive.
- **Branches:** do not modify, delete, rename, force-push, or merge `main`, `exp/zai-architectural-circuits`, `exp/zai-autonomous-fullstack`, `exp/zai-visual-intelligence`, historical experiments, or the open PR branch.
- **Honest claims:** external controller skill ≠ permanent weight learning. Single-shot UI ≠ full-stack application. Custom visual scores ≠ independent design quality.

## Useful prior milestones to study without modifying

- `exp/zai-autonomous-fullstack`: Session 033 TaskFlow full-stack staged generation, reported and later audited.
- `exp/zai-visual-intelligence`: Session 034 recovered TaskFlow v2 and MediVault Lite browser-only apps; provenance remains partly unverifiable because raw generation logs were lost.
- `exp/zai-architectural-circuits`: independent architectural/weight-space work by Z.ai.
- `exp/24-transfer-pattern-memory`, `exp/28-learner-transfer`, `exp/32-fim-selfrepair`: related historical techniques; compare without rewriting their results.

See [BRANCH_REGISTRY.md](./BRANCH_REGISTRY.md) for branch ownership and retention rules.

## Primary research references

- Yao et al., [ReAct](https://arxiv.org/abs/2210.03629) — alternating reasoning and action.
- Shinn et al., [Reflexion](https://arxiv.org/abs/2303.11366) — verbal feedback without weight updates.
- Jimenez et al., [SWE-bench](https://arxiv.org/abs/2310.06770) — realistic software task evaluation.
- Yang et al., [SWE-agent](https://arxiv.org/abs/2405.15793) — tools/interface for software agents.
- Hu et al., [LoRA](https://arxiv.org/abs/2106.09685) — background only; presently prohibited by AGENTS.md.
- Finn et al., [MAML](https://arxiv.org/abs/1703.03400) — conceptual meta-learning research, not proof of performance on this hardware.
