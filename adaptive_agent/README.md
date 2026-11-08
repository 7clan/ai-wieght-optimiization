# Adaptive generalization controller — Milestone 1

This is a **tested controller prototype** for our frozen Qwen2.5-Coder-0.5B research. It has **not** made the model intrinsically smarter, run a full application benchmark, or modified weights.

## Implemented

- Typed task contracts with explicitly **public** acceptance criteria.
- A bounded propose → search/test → diagnose → retry loop.
- Automatic documentation escalation after two failed public attempts, even if the model doesn't request help.
- Duplicate-proposal detection to avoid wasting CPU on the same failed artifact.
- Generalized failure families (API contracts, data contracts, dependencies, UI layout, logic) rather than hard-coded fixes for particular tasks.
- Structured citations for documentation evidence and experiment reports with artifact hashes.
- A JSON-only Qwen adapter that can be supplied with the repository's *existing* frozen-model inference function.
- A sandbox evaluator interface; the controller refuses to invoke a non-isolated evaluator.

## Run the currently available tests

From the repository root:

```bash
python -m unittest -v tests.test_adaptive_controller
```

These tests use deterministic fake models, fake documentation, and a fake evaluator that **never executes generated source**. They demonstrate controller behavior, **not** end-to-end coding ability, real isolation, or benchmark improvement.

## Next engineering milestones

1. Build a *real* resource-limited, network-disabled, unprivileged Docker evaluation adapter. A boolean `is_isolated` marker is a programming interface, **not** proof of security; do not connect an arbitrary shell executor.
2. Connect official documentation retrieval with verifiable URL, content and citation capture, enforce allowed domains for each task, and cap result size.
3. Run the optional `load_local_qwen()` adapter only in a suitable environment with a cached 0.5B checkpoint; measure actual RAM/CPU, record prompts, seeds and model tokens. No other model should be loaded alongside it.
4. Freeze public and private full-stack tasks before evaluation. Keep private test cases inaccessible to model and selection loops.
5. Compare frozen model without controller (Track A) versus frozen model with controller (Track B), preserving exact provenance for teacher integration and mechanical scaffolding.
6. Only after a **separate explicit user authorization** may the planned Track C/D parameter adaptation override the existing training prohibition in `AGENTS.md`.

## Minimal integration contract

```python
from adaptive_agent import AgentController, Task
from adaptive_agent.qwen_adapter import load_local_qwen

task = Task("inventory-001", "Create an inventory service", ("GET /api/items works",))
model = load_local_qwen()  # Explicit, costly: requires locally cached model/dependencies.

# Provide independently implemented safe Docker evaluator and docs retriever.
# report = AgentController().run(task, model, docker_sandbox, documentation)
```

Never claim a full-stack application is working until browser, API and backend persistence tests pass under real execution. The controller reports `public_checks_passed`, not `generalized` or `learned`.
