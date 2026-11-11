# Session 043 — First Instruct-only offline app attempt

Branch: `exp/043-instruct-real-app`, created from the recovered Session 041C
branch at `ea5769b`. The exact original Qwen checkpoint, merged 041B weights,
and the sealed 24-task holdout are untouched. No fine-tuning, weight editing,
new model checkpoint, or cloud inference was performed.

## What actually ran

The pretrained `Qwen/Qwen2.5-Coder-0.5B-Instruct` model generated a complete
HTML/CSS/JavaScript source file for a local task manager. Inference used CPU
PyTorch, Transformers 4.57.6, greedy decoding, and a deterministic seed.

- Attempt 1: 1,029 generated tokens; 200.73 s wall **including cold model
  download and load**. Preserved unedited at
  `experiments/z043-instruct-app/{raw_completion.txt,index.html,generation_report.json}`.
- Attempt 2: 1,076 tokens; 182.19 s including load. Prompt included only
  explicitly identified *public* source-level defects of the first attempt,
  without a teacher's replacement implementation. Preserved unedited under
  `experiments/z043-instruct-app/revision2/`.
- Both sources meet elementary HTML structural checks and contain real inline
  JavaScript, not just CSS. Structural checks are **not** behavioral passes.

## Actual coding defects — do not claim a working app

The first attempt never created `<li>` elements when submitting a task,
did not prevent form navigation, omitted user-facing completion/delete
controls, and never called its save routine. Its filter logic removed list
item tags instead of controlling task visibility.

The revision fixed some structural issues but still embeds a fixed sample
task array, uses `const tasks` while `deleteTask()` and filter handlers assign
new arrays to it (runtime TypeError), substitutes destructive filtering for
view filtering, omits `localStorage`, and provides no explicit per-task
completion/deletion controls. These are source-level observations, not
claims based on executing generated JavaScript on the host.

The only execution of these generated files is the separate restricted
GitHub Actions Docker behavior job in
`.github/workflows/session043-instruct-app.yml`; it tests user interaction,
filters, mutation, and persistence inside a network-disabled, read-only,
non-root container. Failed checks are real failures.

### Independent Docker execution (completed)

[GitHub Actions run 43025748673](https://github.com/7clan/ai-wieght-optimiization/actions/runs/43025748673)
finished **FAILURE**: provenance and HTML checks passed; Docker image build
passed; the actual model-generated JavaScript failed its behavioral checks.
Four of thirteen checks passed (app renders, add controls present, Completed
and Active filter controls present), and nine failed. In particular, neither
task could be added, no mutation was saved, filtering did not show the
correct data, deletion failed, and reload did not preserve tasks. The
isolated JS runtime raised `Cannot read properties of undefined (reading
'value')` and `Assignment to constant variable.`. This is model output
failure, not a sandbox setup failure.

## Verdict

**NOT A WORKING APP.** The pretrained Instruct model exhibited a better
response structure than its first attempt, but **did not demonstrate the
required functional coding behavior** in this two-attempt trial.

The next proposed approach is an explicit small-model **agent/controller**
that works in bounded pieces (data model, operations, UI wiring), validates
each piece in a restricted container, and gives the model concise actionable
feedback. That could yield a working model-assisted app, but the trusted
controller/scaffold must never be misrepresented as Qwen-written source.

No private holdout was used, and there is no generalization claim.
