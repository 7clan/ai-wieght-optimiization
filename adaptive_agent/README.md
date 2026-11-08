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
- A separately measurable **single-file Qwen adapter**: the model emits raw
  Python/JavaScript source for one contractually named file, then receives its
  own prior file and a real public test error for bounded micro-repair. No
  teacher writes code and the frozen checkpoint is unchanged.
- A sandbox evaluator interface; the controller refuses to invoke a non-isolated evaluator.
- A **DockerSandbox** adapter with fixed Python/Node runtimes, trusted tests,
  network-disabled/read-only/non-root containers, memory and CPU bounds.
- An **OfficialDocsResearch** adapter with HTTPS official-host allowlisting,
  bounded fetching, no redirects, text extraction and SHA-256 provenance.

## Run the currently available tests

From the repository root:

```bash
python -m unittest -v tests.test_adaptive_controller tests.test_adaptive_infrastructure
```

These tests use deterministic fake models, mock documentation and a fake evaluator that **never executes generated source**. They demonstrate controller behavior and Docker command construction, **not** end-to-end coding ability, real isolation, or benchmark improvement.

On a Docker-capable Linux machine where the images have been separately obtained:

```bash
python -m tests.smoke_adaptive_docker
```

This executes only author-controlled smoke fixtures via the isolated Docker
adapter, checking that both correct and incorrect Python/JavaScript solutions
are scored appropriately. The branch-specific GitHub workflow also runs it.
No Docker is installed in the initial ChatGPT scratch environment, so real
container execution must be verified by the hosted workflow before claiming it
passed. Docker sandboxing is defense in depth, not perfect isolation.

## Experimental real-Qwen pilot

`experiments/adaptive/pilot.py` compares three exploratory frozen-model tracks on
one small Python and one JavaScript challenge. Track A uses a single JSON
proposal. Track B may make up to three JSON proposals and two public evaluations.
Track C uses raw single-file completion and at most four proposals/three public
evaluations, with the exact previous source supplied after a failure.
Private tests are scored *after all tracks finish generation*, never fed back
into candidate selection. The pilot runs no teacher fixes, no search service
(the isolated docs infrastructure has separate tests), and **no training**.

The completed V1 and V2 runs both scored **0/2 public and 0/2 private** in
both tracks; see [the measured log](../docs/ADAPTIVE_PILOT_FINDINGS.md). A
successful workflow run is evidence that the protocol executed, **not** that
Qwen solved either task. V3 is a new hypothesis until its report is audited.

On GitHub Actions, `adaptive-qwen-pilot.yml` attempts the measured 0.5B CPU run
and uploads its report as an artifact. This is a protocol smoke test, **not a
full-stack or independent generalization benchmark**. A failed download or
resource cap must be documented and never replaced with invented scores.

## Next engineering milestones

1. **Recheck the live Docker smoke** after each controller change; a boolean `is_isolated` marker is only an interface convention, not a security proof.
2. Connect the official-documentation search callback to a real source index. The safe fetcher is implemented but does not secretly invent search results; handle unavailable network access explicitly.
3. Compare both frozen `load_local_qwen()` source protocols under CPU limits and measure actual RAM/CPU, prompts, seeds and model tokens. No other model should be loaded alongside it.
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
