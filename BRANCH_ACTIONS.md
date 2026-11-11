# Branch Action Ledger — `exp/zai-041-direct-weight-improvement`

This file is the per-branch action ledger. It exists **only on the
branch named in the title**, so its very presence identifies the
branch you are looking at:

    git show exp/zai-041-direct-weight-improvement:BRANCH_ACTIONS.md   # exists (this file)
    git show main:BRANCH_ACTIONS.md                                     # errors

Every commit created from an action in this ledger also carries the
prefix `[exp/zai-041-direct-weight-improvement]` in its subject.

## Branch facts

- Branch: `exp/zai-041-direct-weight-improvement`
- Forked from: `84dbc39` (SESSION040 final) — **re-created from the same
  commit after the environment reset** on 2026-11-11; the original branch
  creation and the completed SESSION 041A work lived in a sandbox that was
  subsequently reset (see `docs/ZAI_SESSION041A_MEMORIAL.md`)
- Scope guarantee: no action in this ledger writes to any other branch
  or to `main`; every push goes to
  `origin/exp/zai-041-direct-weight-improvement` only
- Work: SESSION 041A — direct weight improvement (closed-form,
  norm-bounded, reversible weight edits against the demo-vocabulary
  copying failure mode). **The experiments were completed in the lost
  sandbox (local commit `d535474`, REJECT verdict: Track B 0/18,
  Track A 0/6 — user-reported). They are NOT repeated.** This branch now
  holds the memorial, the forensic loss record, and any successor work
  the user directs from the surviving checkpoint state.

## Ledger

Rows are append-only. The "Commit" column records the commit that
contains the action; a row is filled in by the next ledger update, so
the newest row may still say "this commit".

| # | UTC time | Action | Outcome | Commit |
|---|----------|--------|---------|--------|
| 1 | 2026-11-11T09:39:00Z | (pre-reset knowledge) Session brief received; PAT auth configured; branch created from `84dbc39` and pushed to origin | Branch on origin at baseline `84dbc39` | (reset) |
| 2 | 2026-11-11T09:40–11:00Z | Successor session (post-reset): model environment restored in foreground chunks (torch 2.15.0+cpu, transformers 5.22.2, HF snapshot) with base safetensors sha256 re-verified == pin `aff8914e…a47f80`; SESSION 041A infra exploration (archcircuits tracing/edits, s039 suite-v2 splits) begun | Environment restored; exploration interrupted by the user's stop-and-report instruction | this commit |
| 3 | 2026-11-11T11:00–12:00Z | Forensic recovery audit for lost commit `d535474`: local history/reflog/fsck/stashes/packed-refs, GitHub API (commit lookup 422, search 0, events, all branches + PR refs, all 22 PAT-visible repos), filesystem sweeps (`rg d535474` over `/home/z` `/tmp` `/root`; artifact-dir search; boot-restore manifest analysis — 213 restored files, `research/` subtree not snapshotted) | **`d535474` declared genuinely unrecoverable**; verdict survives via user report; 041B (`adf668f` on origin) confirmed intact | this commit |
| 4 | 2026-11-11T12:00Z | Memorial + loss report written (`docs/ZAI_SESSION041A_MEMORIAL.md`); this ledger established for the re-created branch; holdout remains sealed and user-gated | Documentation committed; branch pushed | `456d3ea` |
| 5 | 2026-11-11T12:30Z | Resume verification: 041B merged checkpoint regenerated from branch artifacts in the reset environment (torch 2.15.0+cpu / transformers 4.57.1 / peft 0.21.2; worktree at `adf668f`; brief disclosed dev-server pause for RAM); `model.safetensors` sha256 `fc743be4…` **byte-identical to the committed 041B manifest**; working copy staged at `experiments/z041-coding-finetune/merged-checkpoint/` (gitignored via new rule mirroring 041B) | Latest completed checkpoint verified operational; memorial §7 added | this commit |
