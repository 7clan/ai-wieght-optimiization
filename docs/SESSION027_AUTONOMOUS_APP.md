# Session027: genuinely model-completed expense tracker

## What is changing?

The prior FocusBoard was model-assisted: Qwen supplied **eight narrowly scoped
insertion slots** inside a trusted app. PocketLedger is a fresh expense tracker
with a very different data model.

Here Qwen receives a written contract, module filenames and required function
signatures, then completes the logic of **all five application modules**:

1. Python category summarization
2. Node.js JSON-file persistent store
3. Express HTTP API
4. React UI
5. CSS stylesheet

There is no teacher-authored application code inserted into the published
modules. The Docker evaluator does use explicitly labeled test-only reference
implementations to check its own correctness and to isolate module failures.
They are **never** shown to the model, accepted as candidate output or included
in the published app.

## How the mentor teaches

- First collect five greedy, unmodified Qwen completions.
- Run them in an isolated, read-only, nonroot, no-network Docker container.
- Retry failed modules up to three times. The first retry receives the abstract
  Session026 reasoning-pattern memory; later retries receive public test failure
  messages and excerpts of **Qwen's own previous code**.
- Accept only a candidate improving that module's public tests.
- After all choices are frozen, run the untouched greedy and guided modules on
  the same fresh independent holdout fixtures.
- Publish raw attempts, actual generated file bytes, module pass/fail and a
  **static, sanitized** model-rendered React preview, even on overall failure.

Nothing in this experiment updates the 494,032,768 model parameters. The
signatures, build tools, test harness and runtime remain external, so a passing
score is evidence of model-generated application *modules*, **not** an
independently designed deployment infrastructure or senior-engineer parity.

The workflow is `.github/workflows/session027-autonomous-pocketledger.yml`.
See `experiments/session027_autonomous_app_report.json` after the actual
Docker/CPU run completes. A pending run must not be described as successful.
