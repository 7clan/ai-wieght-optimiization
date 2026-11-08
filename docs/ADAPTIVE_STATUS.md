# Adaptive Generalization — Live Handoff

**Date:** 2026-11-08  
**Working branch:** `exp/qwen-adaptive-generalization`  
**Last verified remote commit at handoff:** `48f9ded2b300692664c8632ce69be4ba7671f77e` (may advance after this document is committed)

## Verified now

- Initial controller implementation: `adaptive_agent/controller.py`
- Frozen-Qwen JSON proposal protocol: `adaptive_agent/qwen_adapter.py`
- Engineering/readme: `adaptive_agent/README.md`
- Controller unit tests: `tests/test_adaptive_controller.py`
- Command executed locally: `python -m unittest -v tests.test_adaptive_controller`
- **Result: 9 tests passed**, using deterministic fake model and fake sandbox; no downloaded model, real generated execution, or training.
- GitHub comparison at handoff: new branch was seven commits ahead of `main`, zero behind, containing exactly two roadmap/registry files and five implementation/test files.
- All Z.ai branches and `main` remained untouched.

## Not yet delivered

- No real Docker-backed evaluator integration. The `is_isolated` flag is an interface convention and is not by itself a security guarantee.
- No official documentation retrieval connector with enforced URL/domain/content verification.
- No actual inference using frozen Qwen0.5B on a new problem. `load_local_qwen()` remains explicitly opt-in.
- No real full-stack application, browser screenshot, held-out score or measured generalization.
- No weight adaptation. The current `AGENTS.md` forbids training, LoRA, gradients and optimizers.

## Next autonomous coding task (copy into Codex on this branch)

> Continue the **adaptive generalization controller** from `docs/ADAPTIVE_GENERALIZATION_ROADMAP.md` and `docs/ADAPTIVE_STATUS.md` in branch `exp/qwen-adaptive-generalization`. Work autonomously through the following ordered milestones while respecting `AGENTS.md`. Do not stop after a plan. First inspect branch status and code, run existing nine tests, and establish baseline. Then:
>
> 1. Implement and prove a real CPU-limited, memory-limited, network-disabled, read-only-root, unprivileged Docker evaluator for generated Python and JS/Node, with explicit timeouts, cleanup and tests. Stop on Docker unavailability; never execute generated code unsandboxed.
> 2. Implement an evidence retriever that prioritizes official docs, captures source URLs/content hashes, flags unknown or absent evidence, and avoids feeding untrusted instructions as authoritative directives.
> 3. Connect the frozen Qwen2.5-Coder-0.5B-Instruct checkpoint to bounded JSON proposals; measure RAM, wall time and output validity. Do not download models unless required and available within budget; never load multiple heavyweight models.
> 4. Freeze at least three genuinely new full-stack requirements and a sealed holdout before any model tuning. Run original-model alone and original-model-plus-controller on identical resources and public contracts. Validate backend/API/storage and real browser interactions, not only static JSX/HTML.
> 5. Publish raw provenance, per-task outcomes, metrics, actual screenshots, tests, source attributions, known failures and a reproducible final audit. Clearly distinguish Qwen original, Qwen with repair, teacher integration and deterministic scaffolding.
>
> Limits: ~2 CPU, <=4 GiB peak RAM where measurable; no training/LoRA/backpropagation/weight changes without separate authorization. **Never modify, rename, delete, merge, force-push or otherwise touch `main`, any `exp/zai-*` branch, historical numbered branches, or open PR #1.** No secrets in commits. Commit/push verified checkpoints on this branch only, and keep this status file current. If blocked or resource-limited, document exact evidence and best safe next step instead of guessing. Stop when deliverables pass their acceptance checks or a real authorization/resource blocker is reached.

## Evidence standard

A controller that improves after feedback is **system-level adaptation**. The frozen model's intrinsic weights remain unchanged. Any later claim that Qwen itself learned transferable skills requires a separate authorized parameter-adaptation experiment with an untouched holdout.
