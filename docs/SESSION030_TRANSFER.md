# Session 030: does Qwen transfer its PocketLedger lesson?

**Model:** unchanged base Qwen/Qwen2.5-Coder-0.5B, exactly 494,032,768
parameters. **New target:** ShelfStock inventory manager.

The preceding experiments demonstrated that the model could produce valid CSS
and a correct Python aggregation after observing a teacher's unrelated
example, but independent JavaScript storage/API/React generation still failed.
Session029 produced a working **teacher-corrected** PocketLedger and archived
the three correction pairs. This experiment tests whether those examples
actually help the same frozen small model build a previously unseen app.

## Protocol

1. Freeze a new ShelfStock specification and three public and three different
   private Python datasets. The app has five module contracts: Python summary,
   persistent JSON store, Express API, React UI and CSS.
2. Generate each body once with plain, short specifications—no teacher example.
3. Independently grade public syntax/functionality in bounded, read-only,
   unprivileged, network-disabled Docker.
4. For each failing role, show the **actual working PocketLedger source**
   (teacher-written for store, API and UI; Qwen-written for Python/CSS). Qwen
   must adapt it to ShelfStock and generate NEW target source. Allow one
   further bounded repair based on public feedback.
5. Freeze public selections. Evaluate untouched baseline and teacher-guided
   selections on the same unused holdout values.
6. Publish every raw completion, full prompts, measured CPU/token budget,
   actual per-module checks, and sanitized script-free preview.

## Critical attribution

No entire ShelfStock module is supplied by the teacher. The target app bodies
are Qwen outputs prepended with minimal signatures/imports. However the mentor
prompts contain **full other-domain reference implementations**, so positive
results would show *in-context guided transfer*, not unaided architecture,
fine-tuning, permanent weight learning or parity with frontier coding systems.

The UI criterion checks hooks, fetch wiring and React server rendering. It is
not a browser click test. Full-app success additionally requires genuine
Python + Express + persisted Node store integration in restricted Docker.
