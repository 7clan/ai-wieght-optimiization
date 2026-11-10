# Superseded evidence: Track C ran with an EMPTY feedback channel

**Defect (found 2026-11-10, Session 040 Phase 5):** `archagent/s040/exec.py`'s
verdict sanitizer returned `{status, passed, candidate_executed, reported_checks}`
WITHOUT the checks list. `experiments.py::_failing_checks` reads
`verdict["checks"]`, so every Track-C repair prompt built by
`prompts.build_track_c_repair` quoted an EMPTY "VERIFIED problems" section —
the execution-feedback treatment never actually delivered feedback.
All 51 repair attempts in the superseded records regenerated with the same
information content as the initial prompt (plus an instruction to fix an
unnamed problem list).

**Impact:** the Track-C arm of the Phase-4 comparison (C 1/18, 0/51 repair
conversions) measured "repair loop with no feedback", not "execution-feedback
repair". Tracks A, B and D are unaffected (no feedback path).

**Fix:** `_parse_verdict` now carries a sanitized check table
(`name`/`passed`/`detail`, detail truncated to 160 chars) with every verdict;
EXECUTION_FAILED and TIMEOUT results carry a synthetic first check
(`exited-cleanly` / `completed-within-wall-clock`). Unit suite: 228 OK.

**Disposition:** the 18 records below are preserved verbatim as
`track-C/`; a fresh Track-C run with the fixed feedback channel replaces
them in `../tracks/track-C/`. Comparisons in the Phase-7 report use ONLY the
re-run records; the superseded set is retained as the defect's evidence.
