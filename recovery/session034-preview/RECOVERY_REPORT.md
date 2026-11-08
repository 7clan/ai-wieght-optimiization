# Session 034 Recovery Report

**Date:** 2026-11-08 (recovery session, after sandbox recycle)
**Recovered by:** inspection of the recycled preview workspace
(```/home/z/my-project```, local git commit ``363767d`` dated
2026-11-08T04:04:21Z, author "Z User" — the previous Session 034
agent's auto-commit) plus the live preview working tree.

## 1. What was recovered (this directory, SHA-256 in MANIFEST.sha256.json)

| Artifact | Files | State |
|---|---|---|
| **TaskFlow v2** (Goal A application) | 24 (index.html, 9 CSS files, app.jsx, 4 components, 2 views, store.js, filter lib, ORIGIN.json) | complete; file mtimes 2026-11-08 02:22 |
| **MediVault Lite** (Goal B application) | 12 (index.html, 3 CSS files, app.jsx, doc-row-modal, 2 views, store.js, search-filter lib, ORIGIN.json) | complete; file mtimes 2026-11-08 03:47 |
| **taskflow-trackA** (four-track experiment, Track A baseline) | 1 (single-file app) | complete; 03:56 |
| **Real browser screenshots** | 4 PNGs: taskflow-desktop 1440x900, taskflow-mobile 390x844, medivault-desktop 1440x900, medivault-mobile 390x844 | complete; 03:57 |
| **Preview portal page** | preview-portal-page.tsx (the Next.js page that served both apps in iframes + stats) | complete; 04:01 |
| Vendor React 18 + babel-standalone | public/vendor (copied, standard libraries) | complete |

## 2. What was NOT recovered (lost with the recycled sandbox)

- **experiments/zai-visual/generations/** — the raw Qwen generation
  logs (prompts, seeds, token counts, candidate texts). ORIGIN.json
  references these (e.g. ``generations/staged-all-trackD/S3.1-index.json``)
  but the directory does not exist anywhere in the recycled workspace.
- **experiments/zai-visual/reports/** — run reports (e.g.
  ``S5.1-salvage.json`` referenced by ORIGIN.json), the four-track
  A/B/C/D comparison data, and the nine-metric measurements.
- **Visual infrastructure source** — the previous session's evaluator,
  harness and builder code (this recovery session re-created its own
  evaluator/harness/checker/curriculum/css_builder from scratch BEFORE
  the recovery instruction arrived; those are separate, clearly
  authored-by-this-session files under archagent/visual/).
- **docs/ZAI_VISUAL_INTELLIGENCE.md** — the final report.
- Browser-test scripts and their JSON results for the v2 apps.

## 3. Provenance status — what can and cannot be claimed

**HONEST CLASSIFICATION OF THE RECOVERED FILES:**

1. The per-file ORIGIN.json records (qwen-original / qwen-repaired /
   teacher-authored / trusted-scaffolding, with candidate counts and
   repair notes) are *recovered metadata*. They are internally
   consistent and match the file headers (e.g. store.js documents
   R1–R7 repairs).
2. **Lineage replay is NOT possible** for these files: the recorded
   model completions that Session 033 used to hash-verify every
   accepted byte are gone. Therefore the qwen-* attributions below are
   *recorded claims from the previous session*, not re-verified
   provenance. Per the recovery instruction, these files are marked
   ``recovered`` wherever they are cited going forward.
3. Two files are explicitly recorded as **teacher-authored**
   integration layers (both app.jsx files) — consistent with the
   Session 034 method where the harness may assemble but the previous
   agent disclosed authoring these directly.
4. The screenshots are PNG files with plausible dimensions, but the
   *report that independently verified them is lost*. This session
   re-verifies everything it can by direct measurement (below).

## 4. Claims made by the recovered preview page (UNVERIFIED until re-tested)

The recovered portal page displays: TaskFlow v2 browser tests 15/15,
visual score 98%; MediVault browser tests 15/15, visual score 100%.
These numbers were produced by the previous session's own tooling,
which was lost. They are treated as **claims, not measurements**, until
re-verified by this session's independent evaluator (see
``recovery/session034-preview/reverification.json`` once populated).

## 5. Re-verification performed by THIS session

- [x] Static integrity: all CSS/JS references in both index.html files
      resolve to recovered files; vendor libs present.
- [x] Real-browser smoke + independent 10-metric/5-viewport visual
      evaluation (this session's evaluator, written before recovery).
- [x] Functional browser tests: re-run independently (TaskFlow v2
      15-step suite re-implemented against the recovered app's DOM).
- Results recorded in ``recovery/session034-preview/reverification.json``.

## 6. Rules going forward (per recovery instruction)

- Recovered application files are NEVER overwritten silently; any
  modification happens in new versioned copies with disclosed diffs.
- No recovered file may be cited as a new model generation. Only files
  produced by this session's frozen-model runs (with full generation
  logs under experiments/zai-visual/generations/) carry re-verifiable
  Qwen provenance.
- Session 033 history is untouched (exp/zai-autonomous-fullstack branch
  and its committed reports remain exactly as pushed).
- Model-inference work continues ONLY for what is genuinely missing:
  the lost generation logs cannot be "regenerated" (that would be
  fabrication); instead the missing measurements (four-track
  comparison, visual-metric tables) are re-run against the recovered
  apps where the apps themselves suffice, and clearly missing
  infrastructure is rebuilt with fresh, fully-logged Qwen runs.
