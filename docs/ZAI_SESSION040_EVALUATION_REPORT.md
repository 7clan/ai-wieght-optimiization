# SESSION 040 — Scientific Evaluation Report (Phase 7)

**Date:** 2026-11-10
**Branch:** `exp/zai-040-autonomous-fullstack`
**Model:** `Qwen/Qwen2.5-Coder-0.5B`, safetensors sha256 `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80` (re-verified after the environment restore; architecture check 494,032,768 params / 24 layers / 896 hidden on every load). No gradients, no adapters, no weight edits at any point.
**Suite:** frozen Curriculum **v2** (suite_version 2), train+dev splits only: 3 domains (aquarium, observatory, radiostation) × 6 skills = **18 paired tasks**. The 24 holdout tasks stayed sealed for the entire session (verified: every evaluator refuses the holdout split; no holdout read occurred).
**Execution tier:** `UNSHARE_USERNS_DISCLOSED` (pivot_root'd user+mount+net+pid namespaces, RO binds, tmpfs /work + noexec /tmp, capability-drop, rlimits, wall-clock group kill); the Docker argv for CI parity is preserved in `archagent/s040/exec.py`. Every evidence record labels its tier; `model_weight_change: false` and `candidate_executed` are recorded per verdict.

---

## 1. Executive summary

1. On the frozen v2 suite, **all controller treatments score at or near zero**: A (unassisted) 0/18, B (contract-first) 1/18, C (B + execution-feedback repair, re-run with a verified feedback channel) 1/18 — the same single pair B solved — and D (controller decomposition, react/integration only) 0/6. The previously replicated contract-first effect (037: A 4/15 → B 9/15 on v1-style tasks) does **not** transfer to v2 at measurable magnitude: the suite's difficulty floor is above what prompt-side assistance can reach with this checkpoint.
2. **Where the signal actually is:** the failure taxonomy. 11 of 17 Track-B failures contain greenhouse-demo vocabulary in the candidate (the model copies the in-context example's domain words instead of mapping the task's own nouns); 5 of 17 crash on execution; the rest fail behavior probes with task-correct vocabulary. This replicates and sharpens the 038A finding: the binding constraint is **in-context example dominance**, not lack of contract detail.
3. **Execution-feedback repair is now cleanly falsified at this scale — twice.** In the re-run, 34/51 repair prompts quoted verified failing checks with concrete counterexamples (e.g., `search: row.feedGrams.toLowerCase is not a function`), and **0 of 17 failing pairs converted**. Combined with 038A (R 8/15 vs B 9/15, p = 1.0), feedback repair has now failed under both empty and information-rich feedback regimes.
4. **The harness defect record:** the first Track-C run (and the first two app pieces) executed with an empty feedback channel — the verdict sanitizer dropped the check list, so repair prompts quoted no problems. The defect was found, fixed, unit-tested (228 OK), disclosed, and the affected records were superseded and re-run (`tracks-superseded-empty-feedback/`). Final numbers use only the re-run.
5. **The applied outcome (Phase 5/6):** under the same contract-first recipe in a fresh domain, the model produced a byte-verbatim POST route with flawless validation semantics (400/404/409/201), a repairable invariant (one feedback round converted it — the technique's clearest success in the session), and two component cores needing 3 disclosed bug fixes plus vocabulary corrections; the schema piece failed all probe rounds. The integrated app passes 25/25 API tests, 7/7 invariant cases, and a full browser interaction suite with zero page errors. Qwen-attributed bytes ≈ 20% of the integrated app, concentrated in logic rather than boilerplate.

---

## 2. Design

| Track | Treatment | Pairs | Isolates |
|---|---|---|---|
| A | minimal public-contract prompt, single-shot | 18 | model-only pass@1 |
| B | contract-first single-shot (concept + domain-disjoint demo + bounded spec + checklist + anchor) | 18 | contract-first elicitation (B − A) |
| C | B attempt-1, then ≤ 3 full-context regenerations quoting the evaluator's failing checks | 18 | execution-feedback repair |
| D | controller-issued 2-piece decomposition (react + integration only), deterministic assembly | 6 | decomposition |

Paired sample: identical tasks across tracks; greedy decoding; deterministic seed per (track, task) via `seed_for`; L-TRIM brace-balanced extraction with one forced-continuation retry on near-empty output; identical evaluators and final scoring across tracks; per-pair state reset (fresh staging per evaluation); fail-closed verdicts (single `S040-RESULT` marker, valid JSON, non-empty checks, all passed). Track C's attempt-1 reuses Track B's recorded attempt (prompt-sha recorded) so the treatment deltas are exactly the repair rounds.

Costs are logged per generation (new tokens, seconds, seed) and per pair (wall clock including restricted-tier evaluation).

## 3. Results

### 3.1 Pass rates

| skill | A | B | C | D |
|---|---|---|---|---|
| schema-relationship | 0/3 | 0/3 | 0/3 | – |
| state-invariant | 0/3 | 0/3 | 0/3 | – |
| api-get-filter | 0/3 | 0/3 | 0/3 | – |
| api-post-validation | 0/3 | **1/3** | **1/3** (carry-over) | – |
| react-interaction | 0/3 | 0/3 | 0/3 | 0/3 |
| fullstack-integration | 0/3 | 0/3 | 0/3 | 0/3 |
| **total** | **0/18** | **1/18** | **1/18** | **0/6** |

Split view: the only pass is on train (observatory:api-post-validation); dev (radiostation) is 0/6 under every track.

### 3.2 Verdict statuses

| track | BEHAVIOR_FAIL | EXECUTION_FAILED | BEHAVIOR_PASS |
|---|---|---|---|
| A | 10 | 8 | 0 |
| B | 12 | 5 | 1 |
| C (re-run) | 11 | 6 | 1 |
| D | 6 | 0 | 0 |

EXECUTION_FAILED was verified candidate-side (the verdict records `candidate_executed: true` with the process exit code; inspected crashes include `request.nextUrl` on a standard `Request` — a genuine model error, not a harness fault).

### 3.3 Costs

| track | pairs | generation tokens | generation seconds | wall seconds (incl. evaluation) | tokens/pair |
|---|---|---|---|---|---|
| A | 18 | 5,002 | 586 | 651 | 278 |
| B | 18 | 10,500 | 1,274 | 1,341 | 583 |
| C | 18 | 40,050 | 4,947 | 3,930 | 2,225 |
| D | 6 | 2,241 | 291 | 303 | 374 |

Track C spent ~2.2k tokens/pair (≈ 3.8× B) for zero conversions; D spent 374 tokens/pair — more token-efficient than B but with no passes (mirroring 037's engine-track economy result).

### 3.4 Repair efficiency (Track C, fixed channel)

- 17 failing pairs entered the loop; 51 repair attempts executed.
- 34/51 repair prompts carried concrete failing checks (repairs 2–3 always; repair-1 quotes the frozen pre-fix Track-B verdict and is empty — the residual limitation of the supersession design, disclosed).
- **Conversions: 0.** First-repair success: 0/17.
- Feedback content was verifiably actionable in the information-theoretic sense — examples quoted to the model include `schema-builds: Error validating: This line is invalid…`, `search: row.feedGrams.toLowerCase is not a function`, `status-filter: count=0 status=scheduled` — and the model still could not act on it.

### 3.5 Failure taxonomy (Track B, 17 failures)

| mode | count | notes |
|---|---|---|
| demo-vocabulary copying | 11 | greenhouse words (sensor/greenhouse/calibrating/monitoring/reading) present in the candidate; includes all 3 react failures and 3/3 invariant failures |
| execution crash | 5 | candidate exits non-zero inside the restricted tier (e.g., `request.nextUrl`) |
| behavior-only failure | 5 | task-correct vocabulary, wrong semantics (probe-level: where-construction, optionality, envelope shape) |
| near-empty / unbalanced | 0 | L-TRIM + forced-continuation retry eliminated the extraction failure class | 

(Modes overlap: crash + demo-vocab co-occur in 3 records.)

## 4. Scientific-integrity event: the empty feedback channel

**What happened.** The Phase-4 Track-C run and the first two Phase-5 app pieces executed with `exec.py`'s verdict sanitizer returning no `checks` list. `_failing_checks` therefore fed `build_track_c_repair` an empty table: all 51 original repair prompts said "Your previous attempt had these VERIFIED problems:" followed by nothing.

**How it was found.** Not by a failing test — by reading the first app repair prompt during Phase-5 integration (the invariant piece was failing a case the candidate obviously mishandled, yet the prompt quoted no problems). This repeats the project's standing lesson that harness defects surface only when artifacts are read, not when suites go green.

**What was done.** Fix (sanitized check table travels with every verdict; EXECUTION_FAILED/TIMEOUT carry synthetic first checks), full unit suite re-run (228 OK), defect README + verbatim preservation of the 18 affected records in `tracks-superseded-empty-feedback/`, complete Track-C re-run with the fixed channel, and disclosure here. The app pieces were regenerated under the fixed channel.

**Residual limitation.** Track-C repair-1 prompts still quote the frozen Track-B attempt-1 verdicts (recorded pre-fix, no checks). Repairs 2–3 quote live verdicts. The 0-conversion result holds on the 34 information-bearing prompts; an unqualified claim about repair-1 specifically is not made.

## 5. The applied outcome (Phases 5–6, summarized)

Spec frozen and committed (`b6c24971…`) before generation; domain `gearhut` disjoint from all 12 known v2 domains (holdout sealed, untouched). 9 generations, 4,550 tokens, 562 s. Outcomes per piece: invariant **QWEN-REPAIRED** (the session's only feedback-repair conversion, on a 7-case boolean contract), POST route **QWEN verbatim** (validation semantics exactly to contract), manager and list **QWEN cores + disclosed corrections** (3 real bugs in the manager: missing error-state declaration, null-initial list crash, wrong input max; vocabulary corrections in both — the same demo-copying mode seen in the tracks), schema **TEACHER-CORRECTED** (failed probes: optional FK + SetNull vs required + Restrict, missing label field, degenerate follow-on models). Verification: API 25/25, invariant 7/7, browser interaction suite clean (filters, empty state, create-without-reload, duplicate error with form preservation, advance, delete, 320 px zero-overflow, sticky footer 0-gap, zero page errors), desktop + mobile screenshots from the live browser. Byte attribution: 4,977 Qwen-candidate bytes inside a 24,268-byte integrated app (~20%), with the honest qualifier that the Qwen share is logic-concentrated while the teacher share is schema + assembly + chrome.

## 6. Comparison with prior sessions

| session | suite | A | B | C/R | D |
|---|---|---|---|---|---|
| 037 | v1-style, 15 tasks | 4/15 | 9/15 | 6/15 | 6/15 |
| 038A | fresh v1-style, 15 tasks | – | 9/15 | 8/15 (p=1.0) | – |
| **040** | **v2, 18 tasks** | **0/18** | **1/18** | **1/18 (0/17 conversions)** | **0/6** |

The collapse is suite-driven, not pipeline-driven: v2 adds two skill families with no prior oracle (react, integration — 6/18 pairs), and its four legacy families carry stricter contracts (schema probes now pin onDelete semantics, status defaults and relation sides; route envelopes pin `total`; the invariant contracts add parent-coupled clauses). Under contracts of this tightness the checkpoint's in-context example dominance becomes the binding constraint — exactly the profile the Phase-8 training proposal must target. Notably, the same model under the *same* recipe produced a contract-exact POST route in the app domain on attempt 1 — the capability exists in slices; the v2-style multi-constraint surfaces are where it fails.

## 7. Conclusions

1. **Elicitation is saturated.** Four prompt-side treatments spanning the shortlist's top techniques moved the v2 score by at most one pair. Any further controller work on this checkpoint has an expected ceiling near zero on v2-difficulty contracts.
2. **Feedback repair is falsified at 0.5B** (two regimes: empty — by defect, information-rich — by design; 0/17 and 0/51→0 conversions respectively). The Phase-3 hypothesis "minimized counterexamples will convert near-misses" is rejected *for this checkpoint*; it remains open for larger models.
3. **Demo-vocabulary copying is the dominant, actionable failure mode** (11/17). It is simultaneously the cheapest thing to fix in weights (the model must learn to bind task nouns over example nouns) and the most dangerous to fix in prompts (removing examples collapses structure). This is the primary target specification for weight-level work.
4. **Slices of exact competence exist** (POST-validation semantics byte-verbatim; a repairable invariant) — evidence that the capability is present but not reliable across surfaces, i.e., a calibration/generalization gap rather than an absence.

*No training was proposed or performed. All numbers derive from the archived evidence records cited inline; nothing in this report was simulated, extrapolated or rounded favorably.*
