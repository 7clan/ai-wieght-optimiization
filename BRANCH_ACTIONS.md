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
