# Branch Action Ledger — `exp/zai-unseen-fullstack`

This file is the per-branch action ledger. It exists **only on the
branch named in the title**, so its very presence identifies the
branch you are looking at:

    git show exp/zai-unseen-fullstack:BRANCH_ACTIONS.md   # exists (this file)
    git show main:BRANCH_ACTIONS.md                        # errors

Every commit created from an action in this ledger also carries the
prefix `[exp/zai-unseen-fullstack]` in its subject.

## Branch facts

- Branch: `exp/zai-unseen-fullstack`
- Forked from: `exp/zai-visual-intelligence` @ `a997586ddaa7fa82`
  (the verified Session 034 milestone) on 2026-11-08
- Scope guarantee: no action in this ledger writes to any other branch
  or to `main`; every push goes to `origin/exp/zai-unseen-fullstack`
  only
- Work: Session 035 — UNSEEN FULL-STACK TRANSFER. The frozen
  Qwen2.5-Coder-0.5B system (harness, staged generation, visual
  feedback, repair loop — all recovered from Session 034) is applied
  to an unfamiliar, genuinely full-stack target: StockPilot, an
  inventory management app on Next.js 16 + Prisma + SQLite, with a
  real REST API and persistent storage. Unassisted baseline (Track A)
  vs staged assisted generation (Track D), same frozen checkpoint.

## Ledger

Rows are append-only. The "Commit" column records the commit that
contains the action; a row is filled in by the next ledger update, so
the newest row may still say "this commit".

| # | UTC time | Action | Outcome | Commit |
|---|----------|--------|---------|--------|
| 1 | 2026-11-08T10:40:00Z | Recover Session 034 assets by fetching `exp/zai-visual-intelligence` from origin and creating this branch at its tip `a997586` in a linked worktree (`/home/z/s035`); local sandbox is a recycled environment (3rd reset), so model runtime (torch 2.15.0+cpu, transformers 4.57.1) and the frozen checkpoint are re-downloaded and re-verified | Branch created; harness tree recovered intact | this commit |
| 2 | 2026-11-08T10:45:00Z | Freeze the StockPilot specification and acceptance tests BEFORE any generation: `experiments/zai-fullstack/SPEC.md` (data model, API contract, UI contract incl. frozen accessible names, responsive bar, protocol, scoring) + `apitest.mjs` (16 checks) + `uitest.mjs` (20 checks) | Freeze committed ahead of all generation | this commit |
| 3 | 2026-11-08T11:00:00Z | Build the Track D harness: pet-shelter-domain demos, mechanical installer (marker-line file extraction), Track A monolithic runner, scoped compile gates (`tsconfig.gate.json`, eslint src) | Harness ready | `0e8462e` |
| 4 | 2026-11-08T11:22:00Z | **Track A (unassisted baseline) complete**: 7/7 monolithic candidates generated (8,400 tokens, 1,251 s wall, 1,882 s CPU, 3,258 MB peak RSS); 0/7 viable — no valid InventoryItem schema anywhere, all installs fail tsc (truncated JSX / syntax), page+API 500, 0/36 frozen checks reachable | Baseline recorded; raw completions archived | `b1a4c31` |
| 5 | 2026-11-08T12:05:00Z–15:55:00Z | Track D staged run + harness calibration (all disclosed): bug #1 brace-balance on completion without anchor (3 valid schema samples wrongly rejected); bug #2 installer dropped the anchor line; bug #3/#3b `_balanced_end` counted signature parens + EOL heuristic inside multi-line signatures (twice-rejected sample trims to a perfect file); bug #4 prompt-echo regions poisoned installs (two-phase `strip_prompt_echo`); client contract dropped after honest 2×12-sample echo failure (data layer inlined into the hook); demo-echo blacklist completed; route-id spec rewritten in code-action style | schema FAILED 3×4 then repaired by first FIM micro-patch (QWEN-REPAIRED, Session-032 method transfers); types accepted r0 k1 (QWEN-ORIGINAL); routes kept failing | `2679231` `264b8a7` `cf59c44` `88f347f` `42bad99` `7adb7ac` |
| 6 | 2026-11-08T15:33:00Z | **False-acceptance postmortem**: the two "accepted" route files were anchor-only (import line + trimmed-to-nothing) — tsc+eslint pass vacuously with no semantic gate; exports-presence gate added; route files reverted and regeneration launched | trackD8/D9 regeneration honestly failing (missing exports, demo echo, one TS2322 near-miss r0_k3); FIM-with-long-instructions echoes instructions (archived); body-granularity contracts cross-contaminate without per-body syntax gates | `2e5938a` |
| 7 | 2026-11-08T16:20:00Z | Save progress: commit trackD8/D9 regeneration samples + logs; ledger backfilled (rows 3–6); branch pushed to origin | this commit | this commit |
