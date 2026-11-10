# SESSION 040 — Final Report

**Session:** 040 — "Autonomous full-stack generation with the frozen 0.5B"
**Branch:** `exp/zai-040-autonomous-fullstack` (base `f0604c9`; all checkpoints pushed)
**Model:** `Qwen/Qwen2.5-Coder-0.5B` — safetensors sha256 `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`, re-verified after the environment restore. Frozen throughout: no gradients, no adapters, no weight edits.
**Hard constraints honored:** main and all experiment branches preserved; PR #3 NOT merged; no CI dispatched; no billable resources created; model code executed only inside the restricted tier (unshare userns disclosed tier locally, Docker argv parity for CI); the 24 holdout tasks sealed for the entire session; every phase committed and pushed as a checkpoint; nothing simulated or falsified — including one harness defect that was found, disclosed, fixed, and re-run at full cost.

---

## Phase ledger

| phase | status | headline |
|---|---|---|
| 1. CI registration | COMPLETE (038B-era, re-verified) | PR #3 open (1 file, byte-identical to the reviewed 821cc89 copy), not merged; workflow/GHCR security review: no blocking findings |
| 2. Behavioral evaluators | COMPLETE | dual-backend restricted execution layer; react-interaction + fullstack-integration + schema evaluators; 15 + 3 controls all oracle-validated IN the tier |
| 3. Coding-process research | COMPLETE | 8 techniques with falsification criteria; lead-review appendix ties each to the measured outcome; lesson #9 added |
| 4. Track experiments | COMPLETE (re-run for C) | 60 paired fail-closed records on frozen v2 (A 0/18, B 1/18, C 1/18, D 0/6); full logs: prompts, hashes, tokens, wall time, attribution |
| 5. Application | COMPLETE | GearHut spec frozen + committed BEFORE generation; 9 generations; per-file byte attribution; archived to `apps/gearhut/` |
| 6. Demonstration | COMPLETE | live preview at the sandbox `/`; API 25/25; invariant 7/7; full browser interaction pass; desktop + mobile screenshots; known-issues list |
| 7. Scientific evaluation | COMPLETE | `docs/ZAI_SESSION040_EVALUATION_REPORT.md` — pass rates, repair efficiency, failure taxonomy, costs, integrity event |
| 8. Training preparation | COMPLETE (no training) | dataset card, 3 new verified candidates, 6 contrastive leads, training proposal with frozen eval plan and pre-declared success criteria |

## The six mandated summary items

**1. What was attempted.** Move the frozen 0.5B toward autonomous full-stack generation by (a) completing the missing behavioral oracles (React interaction, full-stack integration, schema probes), (b) running the four-track controlled experiment (unassisted / contract-first / execution-feedback repair / decomposition) on the frozen v2 curriculum, (c) generating a complete CRUD+validation+tests application under a spec frozen before generation, and (d) preparing — not running — a training proposal aimed at the measured failure modes.

**2. What worked.**
- The evaluator completion: three new oracle families, 18 controls validated inside the restricted tier, zero evaluator-defect findings in the final runs (the one defect found was in the feedback plumbing, fixed with new regression tests — 231 unit tests + 30 adversarial checks green).
- The applied pipeline: under the same contract-first recipe, the model produced a **byte-verbatim, contract-exact POST route** (400/404/409/201 semantics; 25/25 API suite) and an invariant that **one feedback round repaired to 7/7** — the session's only repair conversion, and proof the fixed channel can work when the failure is a near-miss.
- The end-to-end demonstration: a working, responsive, error-handling GearHut app at the preview surface with disclosed per-file attribution.

**3. What failed.**
- All four tracks on v2: A 0/18, B 1/18, C 1/18 (the same pair), D 0/6. The 037-era contract-first effect does not transfer to v2-difficulty contracts at measurable magnitude.
- Execution-feedback repair: 0/17 conversions even with 34/51 repair prompts quoting concrete counterexamples. Falsified at this scale in both the defective (empty) and fixed (information-rich) regimes.
- The model's schema generation: all probe rounds failed (optional FK, SetNull, missing label, degenerate models).

**4. What was learned.**
- **Demo-vocabulary copying is the dominant failure mode** (11/17 contract-first failures): the model binds to the in-context example's nouns, not the task's. This is the primary target specification for weight-level work.
- **The feedback path is part of the treatment** (lesson #9): the empty-channel defect was invisible to every green suite and surfaced only by reading artifacts. Feedback plumbing now has its own assertions.
- Slices of exact competence exist (POST-validation semantics, repairable invariants) — a calibration/generalization gap, not an absence of capability.
- The v2 suite's difficulty floor sits above everything prompt-side assistance can reach with this checkpoint.

**5. Artifacts (all on-branch, evidence-chained).**
- `archagent/s040/` — execution layer, six evaluator families, drivers, harness runners
- `experiments/z040-autonomous-fullstack/` — 60 track records + manifest, superseded set with defect README, app spec/evidence/ATTRIBUTION, training-prep package
- `apps/gearhut/` — the archived application (source, tests, seed, screenshots)
- `docs/ZAI_SESSION040_{WORKFLOW_SECURITY_REVIEW,CODING_PROCESS_RESEARCH,EVALUATION_REPORT}.md`, this report
- Live preview: the sandbox Next.js `/` route (dev server, port 3000)

**6. Next steps (each requiring explicit authorization).**
- Merge PR #3 (CI registration) — maintainer decision, unchanged.
- A separately-authorized training session executing `training-prep/TRAINING_PROPOSAL.md` (LoRA Stage 1 on the 25 verified candidates; GPU-class resources required; the frozen evaluation plan and success criteria are pre-declared).
- After predictions are frozen: unseal the 24 holdout tasks for the post-training evaluation ceremony.

## Cost accounting (generation only; evaluation wall clock in the Phase-7 report)

| activity | tokens | model seconds |
|---|---|---|
| Track A | 5,002 | 586 |
| Track B | 10,500 | 1,274 |
| Track C (re-run) | 40,050 | 4,947 |
| Track D | 2,241 | 291 |
| GearHut app | 4,550 | 562 |
| **total** | **62,343** | **7,660** |

*Report generated at session close. Every number above traces to an archived evidence record; the complete per-phase commit chain is on the branch.*
