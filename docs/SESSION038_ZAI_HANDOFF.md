# Z.ai handoff — Session 038A: Independent Replay and Fresh Generalization Retest

You are continuing the Qwen Architect research project in the user's repository:
`https://github.com/7clan/ai-wieght-optimiization`.

**Do the experiment, not just a plan.** This task is CPU/runner work that the
ChatGPT preparation environment cannot execute: Docker and the Qwen model
runtime are unavailable there.

## Branch ownership and recovery

- Latest completed Z.ai milestone: `exp/zai-generalization-engine-037` at
  `f0b541f09c8d5c6a329262cd41b02b0fa378bece`.
- New read-only preparation artifacts: branch
  `exp/qwen-finetune-readiness-038`, including
  `docs/SESSION038_READINESS.md`,
  `archagent/finetune/audit_archives.py`, and
  `archagent/finetune/candidate_queue.py`.
- Create **your own** branch `exp/zai-038-independent-retest` from the
  current ChatGPT readiness branch. Do **not** commit to either source
  branch, `main`, or branches other agents are using.
- Read `AGENTS.md` first. It prohibits training and LoRA; **do not train**
  or edit that restriction in this session.
- Keep checkpoint/resume state and push after each major phase. Avoid
  repeated model downloads or regenerating any finished work.

## Baseline facts to preserve

Session 037's untouched frozen comparison remains the official result:

| Track | Completed | Generated tokens |
| --- | ---: | ---: |
| A unassisted | 4/15 | 21,844 |
| B fixed | 9/15 | 20,170 |
| C structural | 6/15 | 7,078 |
| D adaptive | 6/15 | 6,696 |

The novel engine did **not** beat the baseline. It did improve schema
relations to 6/6, while an overly small generation cap truncated some
invariants. Its original runner also had cross-track contamination and
route-probe bugs, which were corrected and disclosed.

## Phase 0 — recover and verify

1. Confirm the exact model checkpoint SHA-256 from Session 037.
2. Reproduce the new preparation tests and audit:
   ```bash
   python -m unittest tests.test_finetune_audit tests.test_candidate_queue -v
   python -m archagent.finetune.audit_archives --repo . \
     --out experiments/finetune-readiness-038/archive-audit.json
   python -m archagent.finetune.candidate_queue --repo . \
     --out experiments/finetune-readiness-038/candidate-queue.jsonl \
     --summary experiments/finetune-readiness-038/queue-summary.json
   ```
3. Expected archive screen: 571 prompt/candidate records, 22 traceable
   in-loop accepted unique outputs in the initial replay queue, **zero**
   training-approved. Investigate any count drift rather than silently
   replacing results.
4. Confirm `archagent/verify/adversarial.test.mjs` still passes 30/30.

## Phase 1 — independent replay of candidate solutions

The queue contains *references*, not trusted training examples.

- Resolve each item from its recorded generation path and ledger hash.
- Validate model provenance and exclude teacher-written bytes.
- Reconstruct the complete contract and dependencies from the pinned
  experiment specification.
- Execute candidate code and tests **only in the approved network-disabled,
  resource-limited, unprivileged Docker sandbox**. If Docker or an
  equivalent pre-approved isolation environment is unavailable, do not
  execute the untrusted code: report the blocker and limit results to
  static verification.
- Verify Prisma schema, TypeScript syntax, exported methods, behavioral
  API results, side effects, and cases for invariants where applicable.
- Use distinct fresh temporary databases and exact fixture resets.
- Reject truncated, echoed, placeholder, false-accepted, contaminated,
  or behaviorally failing outputs.
- Only tag `independently_verified` after an actual reproducible passing
  test run; retain raw logs, test hashes, and provenance. The audit's
  `training_eligible:false` must not be manually flipped without proof.
- Reject duplicates at the task-family and normalized-code levels;
  publish family-wise counts.

Produce a dataset card and a sanitized training-candidate manifest,
but **no fine-tuning or gradient optimization**.

## Phase 2 — fresh retest of the invariant-cap correction

Build a **new**, independently frozen suite. Do not re-score the old
Session-037 suite as if a post-hoc patch were pre-registered.

- Include at least three distinct task domains and the known challenge
  families: relations, numeric/state invariants, and GET/POST routes.
- Repair the invariant generation budget and prompt/termination shaping
  that caused Session 037's truncations. Budget changes must be declared
  and compared at equal *total* token budgets, not silently given to
  one track.
- Run fixed baseline vs repaired engine with matching checkpoint,
  seeds, contract definitions, and available compute.
- Require live behavioral route verification; `no verdict` cannot
  become a passing route.
- Before every track and domain, clean installed/generated files and
  database state to prevent cross-track contamination.
- Freeze scoring and fixtures before outputs; disclose invalid test
  corrections and preserve the compromised run separately.
- Report paired pass counts, failures per family, unique tasks,
  generated tokens, latency, peak RSS, and uncertainty.

Do not claim the fix worked without a real improvement on the new suite.

## Phase 3 — prepare the eventual fine-tuning experiment

Produce **proposed**, not executed, training plans for:

1. LoRA on model-origin independently verified examples.
2. An explicitly separate teacher-distillation dataset/adapter.
3. A possible preference-pair experiment using verified corrected vs
   verified incorrect examples from the same task.

Provide data volume by family, deduplication rate, context length,
hardware/RAM feasibility, expected cost, and a new holdout policy.
Avoid assuming a 2-CPU/4-GiB sandbox can train an adapter quickly; if
GPU rental is considered, request budget permission first.

## Deliverables and finish criteria

- A report `docs/ZAI_SESSION038A_INDEPENDENT_RETEST.md` with exact
  score deltas and negative findings.
- A verified/quarantined dataset manifest with no raw credentials.
- Original per-candidate test outputs and independent score records.
- Frozen new-suite specification and hash, stored before model inference.
- Reproduction commands, dependency pins, failure taxonomy, and
  resource accounting.
- A push of every checkpoint on `exp/zai-038-independent-retest`.
- An explicit go/no-go recommendation for **separately authorized**
  fine-tuning, based on the number and diversity of truly verified data.

If a phase cannot be completed, retain the evidence, mark it blocked,
and continue safe non-blocked work. Do not fabricate results, inflate
Qwen model attribution with harness or teacher work, or silently lower
quality thresholds.

Remember: **the scientific question is whether Qwen's future
generalization can improve, not whether an assistant can deliver an
application on Qwen's behalf.**
