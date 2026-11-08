# Frozen Qwen 0.5B: adaptive controller pilot log

These are measured exploratory protocol smoke tests, **not** a benchmark of full-stack competence. They do not show generalization or weight updates. The model is `Qwen/Qwen2.5-Coder-0.5B-Instruct`, distinct from Z.ai's Session 034 base checkpoint. The run uses the same frozen model instance for all tracks, Docker-isolated tests, two host inference threads, and a 400-token generation budget per response. No private checks are passed to the model, and there are no teacher-written repairs.

## Completed independent runs

| Run | Track | Python public/private | JavaScript public/private | Provenance |
| --- | --- | --- | --- | --- |
| [v1 — 42467678175](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42467678175) | Single JSON proposal | fail/fail | fail/fail | First evidence artifact `13612058599` |
| v1 | Bounded JSON controller | fail/fail | fail/fail | Same workflow/artifact |
| [v2 — 42468044790](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42468044790) | Single JSON proposal | fail/fail | fail/fail | Evidence artifact `13612243507` |
| v2 | Bounded JSON controller | fail/fail | fail/fail | Same workflow/artifact |
| [v3 — 42468606339](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42468606339) | Single JSON proposal | fail/fail | fail/fail | Model & Docker executed; inspect report artifact |
| v3 | Bounded JSON controller | fail/fail | fail/fail | Same workflow |
| **v3** | **Direct single-file controller** | **pass/pass, first proposal** | **fail/fail, three proposals** | Same workflow, distinct protocol |
| [v4 — 42469040868](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42469040868) | Single JSON proposal | fail/fail | fail/fail | Error-header diagnostics restored |
| v4 | Bounded JSON controller | fail/fail | fail/fail | Python advances from parser error to logic TypeError, but does not pass |
| **v4** | **Direct single-file controller** | **pass/pass, first proposal** | **fail/fail, only one distinct attempt** | JS errors on missing callable export |
| [v5 — 42469437753](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42469437753) | Direct single-file controller | pass/pass | fail/fail | Unchanged Python success; JavaScript still fails |
| v5 | CommonJS export-only scaffold | — | fail/untested private | All four model outputs lack detectable function declaration; **zero executions** |

V1 outputs typically misnamed or omitted the exact required module. V2 made required file paths explicit and rejected proposals with missing paths before Docker. That fixed the single-shot path problem, but **did not improve pass rate**. V2 Python still emitted a function signature without an indented body (`IndentationError`); JavaScript errored under Node. The bounded JSON controller made three proposals per task but only one evaluation each: duplicate Python code prevented progress; two JavaScript corrections lacked the required filename. V2 peak RSS: 3,404,228 KiB (~3.25 GiB), so this approach remains near a 4-GiB host budget before accounting for other processes.

V3 **partially validates** the direct-source hypothesis: Python now passes one independent private test in a single generation where JSON-based approaches consistently fail. JavaScript remains broken after three attempted direct-source revisions. V3 peak RSS was 3,403,644 KiB (~3.25 GiB). The model did not learn new parameters; the prompt/protocol changed. This is **1/2 tasks** in a small exploratory pilot, not evidence of general reasoning or transferable full-stack capability.

### Session 034 evidence from the independent Z.ai branch

The [Session 034 report](https://github.com/7clan/ai-wieght-optimiization/blob/exp/zai-visual-intelligence/docs/ZAI_VISUAL_INTELLIGENCE.md) distinguishes *R* (historical record restored from chat logs) and *V* (independently reverified). Z.ai independently reverified TaskFlow v2 at 15/15 browser functional checks plus 10/10 defined visual metrics across five viewports, and MediVault Lite at 10/10 functional plus 10/10 defined visual metrics. The frozen **base** model reportedly produced narrow, exact-shape CSS repairs, while larger tasks had truncation or teacher-integration boundaries. Its harness encountered multiple misdiagnosed defects and evaluator bugs; this underlines the need to audit the evaluator itself. Those successes belong to Z.ai's task-specific staged harness, **not** to the model alone. The current adaptive experiments do not claim these as their scores.

## V3 hypothesis (partially supported) and V4 follow-up

The failure mode suggests the tiny model is spending effort emitting metadata-wrapped, JSON-escaped source files rather than completing a small program. We added an independently labeled **single-file controller** track:

1. Declare one mandatory file path mechanically; the model emits raw source only, not a JSON wrapper.
2. After an error, include the exact previously tested source and the public error in the next model prompt, aiming for one small behavioral correction.
3. Maintain a bounded proposal and Docker-evaluation budget; reject blank output, track hashes, do not synthesize implementation as teacher code, and keep private checks sealed until all generation finishes.
4. Compare *the same frozen model* under three distinct inference protocols: JSON solo, bounded JSON controller, and single-file controller. This tests the **system**, not learned weights.

V4 improved experimental diagnosis without rewriting solutions: it recorded the first line of public exceptions (the previous trace recorded only the stack tail), tagged parser/indentation failures, and included the generic CommonJS module export convention for `.cjs` source. The rerun still failed on JavaScript. Do not reclassify repeatedly viewed private tests as a new independent holdout. Next-stage research should investigate syntax truncation and genuinely independent unseen full-stack tasks rather than expanding a benchmark after seeing its holdout.

### V4 measured diagnosis and V5 planned isolation

V4 verified that the direct Python candidate was identical by SHA to the V3 passing candidate: **21 lines, 746 characters, SHA-256 `8bc3103471c1942cd7c9e55355d4480f95cfdc6c1e584aa32fab28980275b0dd`**. By comparison, the JSON path first emitted only a 26-character function signature and later an 89-character implementation with `TypeError: unsupported operand type(s) for +: 'int' and 'str'` (summing strings instead of booleans). The direct JavaScript source was 9 lines/264 characters but the test error was `TypeError: normalizeTags is not a function`. More explicit CommonJS instructions alone did not solve it; identical proposals led to a no-progress stop.

The V5 experiment isolates *integration* from *algorithm*: a fourth, separately labeled **CommonJS scaffold** track appends the one known export statement `module.exports = { normalizeTags };` only when the model's source already declares `normalizeTags`. This is deterministic harness code, explicitly counted as such. The algorithmic implementation remains entirely Qwen-produced. The experiment records whether the generated implementation is byte-for-byte equivalent (modulo whitespace) to the direct-track candidate, and separately tests the resulting application. If the candidate is otherwise logically wrong, the scaffold must still fail. **Do not count export scaffolding as model learning.**

V5 established that export-only scaffolding was **insufficient**: none of four Qwen outputs declared the contractually named function in the accepted declaration forms. The adapter properly rejected all candidates and executed none. Consequently its private pass indicator is `null` (no candidate), not a success or a meaningful scored failure.

V6 will try an even smaller, explicitly labeled function-body-only track. Qwen supplies all executable algorithm statements; the harness supplies the predetermined declaration `function normalizeTags(items)` and the CommonJS export line. The report records these mechanically supplied lines separately. If still failing, stop iterating on these two pilot tasks and move to a frozen, diverse unseen evaluation set with honest costs and attribution; repeated tuning against the same test cannot establish generalization.
