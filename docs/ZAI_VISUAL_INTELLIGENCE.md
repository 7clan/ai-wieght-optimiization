# ZAI Visual Intelligence & Full-Stack Generalization — Session 034 Final Report

Branch: `exp/zai-visual-intelligence`. Frozen model:
`Qwen/Qwen2.5-Coder-0.5B` (494,032,768 parameters, architecture verified
on load). No gradients, no training, no LoRA, no adapters.

**Evidence tiers used in this report** (this session survived TWO
environment resets; every claim is graded):

- **Tier R (Recovered)** — measured by the previous Session-034 agent,
  recovered from the recycled preview workspace's local git commit and
  the recovered chat history (`recovery/session034-chatlog/`). The raw
  generation logs backing these numbers were lost; the numbers are the
  previous agent's own records, internally consistent but not
  re-replayable.
- **Tier V (Verified)** — independently measured by THIS session
  against the recovered applications, with this session's own
  evaluator and browser tests; every Qwen patch byte re-derivable from
  `experiments/zai-visual/generations/fix_*.json`.

---

## 1. Headline results

**Goal A — TaskFlow v2 (professional project manager):**

| Measurement | Value | Tier |
|---|---|---|
| Functional browser test | **15/15 steps, 0 page errors** | V (re-run independently) |
| Visual metrics (10 checks × 5 viewports) | **10/10** (6/10 for Session-033 v1; 8/10 as recovered; 10/10 after Qwen repairs) | V |
| Qwen-authored proportion | 83% of code lines (32% original + 51% bounded-repaired) | R |
| Visual progression under Qwen feedback loop | 48% → 72% → 82% → 98% (3 rounds, previous agent's scale) | R |
| This session's Qwen repair loop | 4 further defects fixed, all on first model sample | V |

**Goal B — MediVault Lite (independent medical-records app):**

| Measurement | Value | Tier |
|---|---|---|
| Functional browser test (own 10-feature checklist) | **10/10, 0 page errors** | V |
| Visual metrics (10 checks × 5 viewports) | **10/10** (9/10 as recovered; 10/10 after Qwen repairs) | V |
| Qwen-authored proportion | 77% of code lines | R |
| Visual progression | 66% → 100% (previous agent's scale) | R |
| Independent visual identity | slate/violet tokens, folder tabs, records table (vs TaskFlow teal/sidebar/cards) | V (screenshots) |

**Both applications run in a real browser right now** (recovered from
the recycled preview workspace, re-verified, and repaired): TaskFlow
v2 15/15 + 10/10, MediVault 10/10 + 10/10, zero page errors. Real
screenshots: `recovery/session034-fixed/shots/` (1440×900 and 390×844
per app, Playwright, synthetic data only).

**A-vs-D transfer measurement (Tier R):** the same frozen model,
unaided monolithic generation (Track A): 7 candidates, 6 stopped at
~107 tokens (EOS, not budget), best was a 191-line truncated file
with **0 interactive elements in the browser**. Under the full staged
system (Track D): 15/15 + 98% (previous agent's scale). The gap is in
the system, not the weights. Tracks B/C were not run (recorded by the
previous agent as an honest gap).

## 2. What happened across the two resets (disclosure)

1. The previous Session-034 agent started from a **first reset** (all
   Session-033 assets gone), rebuilt the environment, downloaded the
   frozen model by pinned commit hash, and completed both applications
   in the Next.js preview workspace (`public/taskflow-v2`,
   `public/medivault`) — which is why these files survived the SECOND
   reset (this session): the preview workspace persisted while
   `/home/z/research-repo` and `/tmp` did not.
2. This session began the assignment anew, reproduced the Session-033
   baseline (34/34 protocol tests, 15/15 browser test, identical step
   results), built its own visual evaluator + component harness +
   CSS curriculum + repair loop, and pushed checkpoints
   (`f8765c3`, `4dab6e3`).
3. Mid-session, the priority changed to RECOVERY. This session
   recovered 39 application/screenshot files (SHA-256 manifest in
   `recovery/session034-preview/MANIFEST.sha256.json`), recovered the
   previous agent's full chat history (credential-scrubbed), and
   re-verified everything it could measure (Tier V).
4. **What was lost and is NOT fabricable:** the previous agent's raw
   generation logs, four-track A/B/C/D raw data, per-stage reports,
   and its final report. Their headline numbers survive only as Tier R
   records. This session re-ran what the recovered applications
   themselves support (visual + functional verification, repair loop).

## 3. Provenance — the honest ledger

**Recovered application files** (Tier R provenance): each file's
origin was recorded by the previous agent in per-app `ORIGIN.json`
(qwen-original / qwen-repaired / teacher-authored /
trusted-scaffolding, with repair notes inline in file headers). These
records are internally consistent, but the lineage-replay evidence
(recorded model completions) is gone — so qwen-* attributions for the
recovered bytes are *recorded claims*, not re-verified provenance.
Two files are disclosed teacher-authored integration layers (both
`app.jsx`); `index.html` files are disclosed loader manifests.

**This session's patches** (Tier V provenance): four visual defects
found by independent measurement were repaired by the frozen model
under this session's repair loop — every accepted patch is a first-
sample `QWEN-ORIGINAL` generation with full prompt + seed + token
count + sha256 logged:

| Defect | App | Attempts | Lines | sha256 (head) |
|---|---|---|---|---|
| 320px typography (9→8 sizes) | taskflow-v2 | 1 | 6 | d04b6809… |
| touch targets + flex-shrink | taskflow-v2 | 1 | 5 | ec0d3926… |
| button hit areas | medivault | 1 | 9 | 913e86b5… |
| doc-name hit area | medivault | 1 | 6 | 409d4809… |

Model inference for this loop: 2 loaded-model runs, 520 new tokens,
69 s wall-clock (2-CPU fp32). The recovered apps remain untouched in
`recovery/session034-preview/` (read-only); the repaired copies live
in `recovery/session034-fixed/` with a disclosed loader-manifest
`<link>` injection only.

## 4. Research findings (frozen 0.5B + visual system)

**From the recovered session (Tier R) — capability boundary map:**

- Free-form CSS tasks: 3/10 pass (58 generations, 31 min). Long
  token enumerations (30+ variables) exceed the model; grid
  `@media` breakpoints are omitted in 6/8 samples; `:focus` rules
  were a free-form blind spot (never written unprompted).
- Staged exact-shape pieces: near-deterministic success (all 21 v2
  app pieces accepted; all 8 stage-2 components).
- Failure taxonomy over 143 raw candidates: prompt echo
  (including fully-commented "CSS" that passes syntax checks),
  module prior (writes `import React` against the no-build contract),
  enumeration overload, silent spec-truncation (drops trailing
  requirements — reproduced this session: the model wrote 2 of 3
  requested rules twelve times in a row), and syntax-valid but
  behaviorally broken integration code (the real-browser test is
  irreplaceable).
- Method transfer evidence: after TaskFlow's lessons were written
  into the contract, MediVault's store generated successfully on the
  first attempt.

**From this session (Tier V) — harness-side lessons:**

- The model was repeatedly RIGHT when the harness was wrong: 12
  perfect hierarchy patches were rejected because the defect spec
  misattributed the selector (`.card h3` vs the real `.sidebar-label`),
  and 12 correct `flex-shrink: 0` patches were rejected by an
  echo-checker designed for JS vocabulary. Small-model development
  systems need their OWN verification loop debugged with the same
  rigor as the model's output.
- Micro-patch specs (one rule, one property, measured facts in the
  prompt) succeed on the first sample; multi-part specs get
  truncated. Same boundary as Stage 1, now confirmed in the repair
  regime.
- Five evaluator/harness defects were found and fixed with full
  disclosure (calibrations #4 and #5 plus the extraction/echo bugs —
  listed in `recovery/session034-preview/reverification.json`).

## 5. Visual evaluation system (reproducible)

`archagent/visual/evaluator.mjs`: 10 metrics × 5 viewports
(1440×900, 1280×800, 768×1024, 390×844, 320×700), pure DOM geometry +
getComputedStyle (no screenshot similarity): text visibility, sibling
overlap, horizontal overflow, button hit areas (WCAG 2.2), stack
alignment, typography scale, WCAG contrast, interactivity
(cursor + `:hover` rules), heading hierarchy, cross-viewport
responsive adaptation. Five calibrations are documented in-source.
`archagent/visual/harness.mjs` + `check_component.mjs`: per-component
fixtures with per-task acceptance criteria.
`archagent/visual/curriculum.py` + `css_builder.py`: the staged
curriculum (19 tasks) and anchored builder (different-domain few-shot
demos, exact-shape specs, structural + browser gates). All
infrastructure is teacher-authored TRUSTED-SCAFFOLD (test tooling;
no application bytes).

## 6. How to reproduce (this session's Tier V results)

```bash
# 1. serve the fixed apps
cd recovery/session034-fixed && node server.mjs &      # :4196

# 2. visual evaluation (10 metrics x 5 viewports)
node archagent/visual/evaluator.mjs \
  --base http://127.0.0.1:4196/taskflow-v2/index.html --waitfor "#root > div"
node archagent/visual/evaluator.mjs \
  --base http://127.0.0.1:4196/medivault/index.html   --waitfor "#root > div"

# 3. functional browser suites (15 + 10 steps)
BASE=http://127.0.0.1:4196 node archagent/visual/reverify_recovered.mjs

# 4. the Qwen repair loop (fresh model runs, full logging)
ARCHAGENT_MODEL_DIR=<local Qwen2.5-Coder-0.5B> \
  python -m archagent.visual.repair_loop
```

Model: local copy of `Qwen/Qwen2.5-Coder-0.5B`, architecture verified
on load (494,032,768 params). Every generation is seeded; all raw
completions (accepted and rejected) are archived under
`experiments/zai-visual/generations/`.

## 7. What remains open

- Tracks B (staged, no feedback) and C (staged + execution feedback)
  of the four-track comparison were never run; the recovered Track A
  baseline and Track D results stand alone. Re-running B/C against
  the recovered apps is future work.
- Weight-space investigation: not attempted this session (no causal
  localization candidate for visual defects; per the Session-033
  bar, an edit without localization evidence would be unjustified
  curve-fitting).
- The previous agent's 98%/100% visual numbers used its own (lost)
  scale; this session's 10/10 uses the itemized, disclosed,
  five-times-calibrated metric set above. Both are reported; only
  the latter is re-measurable.

## 8. Deliverables map

- `recovery/session034-preview/` — recovered apps (read-only),
  SHA-256 manifest, recovery + re-verification reports
- `recovery/session034-fixed/` — repaired apps (Qwen patches),
  canonical screenshots, serving script
- `recovery/session034-chatlog/` — recovered previous-session chat
  history (credential-scrubbed)
- `archagent/visual/` — evaluator, harness, checker, curriculum,
  css_builder, repair_loop, reverify suite (all TRUSTED-SCAFFOLD)
- `experiments/zai-visual/` — generations (full prompts/seeds/tokens),
  reports, baseline evidence
- `apps/taskflow-qwen/` — Session-033 TaskFlow v1 (untouched history)

The preview portal (`/` route of the Z.ai preview) serves both fixed
applications live in iframes with the real screenshots and the
provenance table.
