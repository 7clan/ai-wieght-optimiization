# Frozen Qwen 0.5B: adaptive controller pilot log

These are measured exploratory protocol smoke tests, **not** a benchmark of full-stack competence. They do not show generalization or weight updates. The model is `Qwen/Qwen2.5-Coder-0.5B-Instruct`, distinct from Z.ai's Session 034 base checkpoint. The run uses the same frozen model instance for all tracks, Docker-isolated tests, two host inference threads, and a 400-token generation budget per response. No private checks are passed to the model, and there are no teacher-written repairs.

## Completed independent runs

| Run | Track | Python public/private | JavaScript public/private | Provenance |
| --- | --- | --- | --- | --- |
| [v1 — 42467678175](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42467678175) | Single JSON proposal | fail/fail | fail/fail | First evidence artifact `13612058599` |
| v1 | Bounded JSON controller | fail/fail | fail/fail | Same workflow/artifact |
| [v2 — 42468044790](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42468044790) | Single JSON proposal | fail/fail | fail/fail | Evidence artifact `13612243507` |
| v2 | Bounded JSON controller | fail/fail | fail/fail | Same workflow/artifact |

V1 outputs typically misnamed or omitted the exact required module. V2 made required file paths explicit and rejected proposals with missing paths before Docker. That fixed the single-shot path problem, but **did not improve pass rate**. V2 Python still emitted a function signature without an indented body (`IndentationError`); JavaScript errored under Node. The bounded JSON controller made three proposals per task but only one evaluation each: duplicate Python code prevented progress; two JavaScript corrections lacked the required filename. V2 peak RSS: 3,404,228 KiB (~3.25 GiB), so this approach remains near a 4-GiB host budget before accounting for other processes.

### Session 034 evidence from the independent Z.ai branch

The [Session 034 report](https://github.com/7clan/ai-wieght-optimiization/blob/exp/zai-visual-intelligence/docs/ZAI_VISUAL_INTELLIGENCE.md) distinguishes *R* (historical record restored from chat logs) and *V* (independently reverified). Z.ai independently reverified TaskFlow v2 at 15/15 browser functional checks plus 10/10 defined visual metrics across five viewports, and MediVault Lite at 10/10 functional plus 10/10 defined visual metrics. The frozen **base** model reportedly produced narrow, exact-shape CSS repairs, while larger tasks had truncation or teacher-integration boundaries. Its harness encountered multiple misdiagnosed defects and evaluator bugs; this underlines the need to audit the evaluator itself. Those successes belong to Z.ai's task-specific staged harness, **not** to the model alone. The current adaptive experiments do not claim these as their scores.

## V3 hypothesis (pending external measurement)

The failure mode suggests the tiny model is spending effort emitting metadata-wrapped, JSON-escaped source files rather than completing a small program. We added an independently labeled **single-file controller** track:

1. Declare one mandatory file path mechanically; the model emits raw source only, not a JSON wrapper.
2. After an error, include the exact previously tested source and the public error in the next model prompt, aiming for one small behavioral correction.
3. Maintain a bounded proposal and Docker-evaluation budget; reject blank output, track hashes, do not synthesize implementation as teacher code, and keep private checks sealed until all generation finishes.
4. Compare *the same frozen model* under three distinct inference protocols: JSON solo, bounded JSON controller, and single-file controller. This tests the **system**, not learned weights.

There is no success claim for V3 until its GitHub Actions report is available and checked. Next-stage research should investigate syntax truncation and longer, genuinely independent unseen full-stack tasks rather than expanding a benchmark after seeing its holdout.
