# Session 028: targeted teacher–student correction

Goal: measure whether a frozen Qwen2.5-Coder-0.5B can improve its *own*
PocketLedger full-stack source by observing **analogous** teacher examples and
the public errors from its preceding Session027 attempt.

## Attribution

- The five source bodies in Session027 were model-completed. Session028 reuses
  its actual selected files, then asks Qwen to regenerate only failing modules.
- Teacher authored unrelated examples (music summaries, bookmark JSON storage,
  library routes, reading-list UI). No PocketLedger implementation is fed as a
  teacher correction. All accepted target source is model output.
- Input/output signatures, Docker checker and preview generator are authored
  infrastructure; their success does *not* imply autonomous architecture.
- Qwen weights stay frozen (494,032,768 parameters). This tests in-context
  pattern transfer; it is **not** fine-tuning or permanent learning.

## Protocol

1. Replay the archived Session027 selected source under a stricter evaluator.
   React must now have state, effects, fetch, form and deletion wiring.
2. For each failing Python, storage, API and UI role, show Qwen a working
   **different-domain** analogy and the latest public failure string.
3. Sample up to three model continuations for each failing role. Execute each
   candidate only in read-only, nonroot, network-disabled, bounded Docker.
4. Accept only public score improvements, role by role. Freeze selection.
5. Evaluate both baseline and selected code on newly authored private values
   unused in Session027. Preserve all model raw text and teacher messages.
6. Publish a sanitized **static** preview and honest independent holdout
   results. A page showing React markup does not establish browser clicks or
   live server operations.

Strong success criterion: all five modules and Python+Express+JSON persistence
integration pass independently. A false or zero score must remain visible.
