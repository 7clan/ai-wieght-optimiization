# Branch Action Ledger — `exp/32-fim-selfrepair`

This file is the per-branch action ledger. It exists **only on the branch named
in the title**, so its very presence identifies the branch you are looking at:

    git show exp/32-fim-selfrepair:BRANCH_ACTIONS.md    # exists (this file)
    git show main:BRANCH_ACTIONS.md                     # errors: does not exist

Every commit created from an action in this ledger also carries the prefix
`[exp/32-fim-selfrepair]` in its subject, so the full action list for this
branch is one command away:

    git log --oneline --grep='\[exp/32-fim-selfrepair\]' exp/32-fim-selfrepair

And every commit unique to this branch since its fork point:

    git log --oneline 6d576ac..exp/32-fim-selfrepair

## Branch facts

- Branch: `exp/32-fim-selfrepair`
- Forked from: `exp/29-selfrepair-deployment` @ `6d576ac3aa200dd` (its tip,
  the Session031 round-36 publish commit) on 2026-11-06
- Scope guarantee: no action in this ledger writes to any other branch or to
  `main`; every push goes to `origin/exp/32-fim-selfrepair` only
- Work: Session032 — FIM-anchored self-repair on the frozen DevMetrics
  contract (frozen Qwen2.5-Coder-0.5B writes every module byte; self-repair
  adds native fill-in-the-middle splices anchored at the evaluator-reported
  failing line; zero teacher bytes; weights untouched)

## Ledger

Rows are append-only. The "Commit" column records the commit that contains
the action; a row is filled in by the next ledger update, so the newest row
may still say "this commit".

| # | UTC time | Action | Outcome | Commit |
|---|----------|--------|---------|--------|
| 1 | 2026-11-06T12:00:00Z | Commit the working Session032 modules that produced sweeps 0-9 (`tinycoder/session032.py`, `session032_worker.js`, `session032_py_worker.py`; compile + AST + node --check verified before commit) | 3 files added; modules are the exact code that generated the recorded state | `cb74d01` |
| 2 | 2026-11-06T12:00:00Z | Open this per-branch action ledger so every later action on this branch is attributable in one place | BRANCH_ACTIONS.md added (this file) | this commit |
| 3 | 2026-11-06T12:00:00Z | First push: publish the branch to the remote as `origin/exp/32-fim-selfrepair`; no other remote branch is created or modified | remote branch created | `32bf76b` (push of `cb74d01`+`32bf76b`) |
| 4 | 2026-11-06T12:20:00Z | Resume the interrupted Session032 run (`--resume`, sweep 9, elapsed 7156.8s of the 14400s wall budget) | first invocation: `fim-compound` ui rejected; a `fim-greedy` ui candidate was **accepted** (public ui wiring improved from 4 missing features to 2) but the invocation then crashed in `save_state`/`verify_lineage` with `KeyError: 'base_sha256'` — a harness schema bug (compound FIM origins record per-op hashes, `rebuild()` expected a top-level base hash). The acceptance was NOT recorded (checkpoint write happens after verification); the deterministic `fim-greedy` job stayed pending on disk | run paused, disk state intact (142 attempts, fim 79/0 accepted) |
| 5 | 2026-11-06T12:35:00Z | Fix the harness lineage-schema bug in `tinycoder/session032.py` `rebuild()`: derive the expected base-module hash from `ops[0].base_sha256` for compound origins, keep the legacy single-splice branch, raise on unrecorded lineages. Model bytes, prompts, selection and acceptance logic untouched; the fix only lets `verify_lineage` replay compound-FIM acceptances (dormant because 0/79 FIM attempts had ever been accepted) | verified: real disk state still verifies; a synthetic compound acceptance replays byte-exactly; tampered fills and tampered op hashes are both rejected | `c82c6bc` |
| 6 | 2026-11-06T13:10:00Z | Add the Session032 publishing pipeline: `tinycoder/collect_session032.py` (FIM-lineage authorship verification — every selected module must replay from recorded model bytes alone — plus live parity gate: refuse to publish unless the local evaluator reproduces the Docker-verified Session031 record) and `tests/test_session032.py` (19 protocol tests: frozen-contract identity, no-teacher-material, metric ordering, FIM helper semantics, lineage replay incl. tamper rejection, collector safety, README block idempotence) | all 19 tests pass (1 skips until the published state exists); template smoke passes with no unresolved placeholders | this commit |
| 7 | 2026-11-06T13:20:00Z | Resume the run after the fix: sweeps 9-12 completed at the module's default rounds cap. The lost `fim-greedy` ui acceptance reproduced deterministically and was recorded (first ever). Decision, disclosed: extend the search to the rounds-40 cap under the SAME frozen 14400s wall budget (Session031 resume protocol; candidate acceptance stays public-metric-only) | extension launched from 9791.0s used | `aa029b9` |
| 8 | 2026-11-06T14:35:00Z | Extension run: sweeps 13-17 to the 14400s wall budget (measured 14642.9s — the module finishes the in-flight sweep before stopping). A SECOND FIM acceptance recorded: `fim-compound` ui sweep 13, own lines 58-86. Totals: 17 sweeps, 276 candidates, 96,734 output tokens, FIM 234 attempts / 2 accepted (both ui surgical splices of the model's own bytes) | final public score plateau [0,1,8,5]: css passes; vs the greedy baseline the run GAINED the delete, summary and logic_structured checks (baseline had 6 completed checks, final 8) but LOST post because the store module's persistence regressed (ENOENT on entries.json), which also blocks integration. ui improved from 4 missing features to 1 (DELETE request only). Holdout unchanged: css only, not integrated | 29c6f72 (run commits in aa029b9..29c6f72) |
| 9 | 2026-11-06T14:40:00Z | Publish: `python -m tinycoder.collect_session032` re-verified every selected module by full FIM lineage replay from recorded model bytes, re-ran the live evaluator parity check against the Docker-verified Session031 record (validated), and published `experiments/session032_selfrepair_{report,predictions,state}.json`, the app under `apps/devmetrics-qwen-fim-selfrepair/`, the live gallery `docs/gallery/session032/` (16 scored sweep pages: live app + report card each), `docs/previews/session032/`, the mission dashboard `docs/index.html` and the README results block. All 19 protocol tests pass (published-state lineage test now active) | published; zero teacher bytes; model bytes deployed exactly as generated | 29c6f72 |
| 10 | 2026-11-06T14:45:00Z | Add the CI workflow `.github/workflows/session032-fim-selfrepair.yml` (workflow_dispatch ONLY, same discipline as Session031's seventh amendment: explicit rounds/wall_budget/resume inputs so no push-triggered run can clobber the cumulative state; Docker evaluator builds plus the session031 trusted positive control; every commit carries the branch prefix and pushes to `origin/exp/32-fim-selfrepair` ONLY; Pages deploy job disclosed continue-on-error with direct raw.githack fallback links) | future measured rounds can now be dispatched from the GitHub UI on this branch alone | 29c6f72 |
