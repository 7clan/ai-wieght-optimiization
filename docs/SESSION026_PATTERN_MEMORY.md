# Session026: transfer-oriented mentor memory (prototype)

We observed two public failure patterns in Sessions023–024: a correct route
result with the wrong JSON response envelope, and an incorrect DELETE method
name copied from an analogous example. The student eventually repaired both.

This experiment preserves those lessons as **abstract instructions** retrieved
by task and domain. Future Qwen prompts can prepend the output of
`python -m tinycoder.mentor_patterns --domain express --task '...'`.

The student is reminded to:

1. Identify the task's exact interface and response contract.
2. Reuse the *structure* of relevant examples, not their unrelated identifiers.
3. Make one bounded edit.
4. Use execution feedback from public tests to classify the cause of failure.

**Verified today:** deterministic memory retrieval, source validation, Python
unit tests. **Not verified:** any improvement on fresh independent tasks.
This is external prompt memory, not permanent neural learning or proof of
general reasoning. Model parameter count remains 494,032,768; no gradients,
fine-tuning, or weight edits. Future measured transfer must compare matched
prompts *with and without* these lessons on fresh frozen tasks, selecting
only against public tests and executing generated code exclusively in isolated
Docker. Private holdouts cannot be mined into the memory bank.
