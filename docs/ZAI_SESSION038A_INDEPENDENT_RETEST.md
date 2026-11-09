# Z.ai Session 038A — Independent Replay and Fresh Generalization Retest

**Branch:** `exp/zai-038-independent-retest` (from `exp/qwen-finetune-readiness-038` @ `2e9ebd8`)
**Model:** `Qwen/Qwen2.5-Coder-0.5B` — safetensors sha256
`aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`,
re-verified this session, identical to the 035/036/037 pin. Frozen;
**no training, no gradients, no LoRA, no weight edits occurred.**
**Session-037 results preserved untouched** (A 4/15, B 9/15, C 6/15,
D 6/15 on `exp/zai-generalization-engine-037` @ `f0b541f`).

---

## 1. Phase 0 — recovery and reproduction (all green)

| Check | Result |
| --- | --- |
| `tests.test_finetune_audit` + `tests.test_candidate_queue` | 8/8 OK |
| `audit_archives` reproduction | byte-identical: 571 records, 0 training-approved |
| `candidate_queue` reproduction | byte-identical: 22 queued, 0 eligible (30 acceptances − 8 dups − 2 contaminated ledgers) |
| `adversarial.test.mjs` | **30/30** (after restoring the StockPilot surface to the workspace from the repo, byte-identical to its backup) |
| frozen-suite manifest | matches (unchanged since 037 freeze) |
| challenge SPEC hashes | run-1 `0f08f72b…`, run-2 `32ac3b42…` both match FREEZE.json (raw-bytes sha256) |
| model checkpoint | sha256 match; loads in 11.1 s; 8-token smoke in 1.13 s |

**Environment:** Python 3.12.16, torch 2.15.0+cpu, transformers 4.57.6
(re-pinned to match 037), node v24.22.2, 2 CPUs, ~3 GiB RAM.
Sandbox reset #3 before this session: ML stack reinstalled, model
re-downloaded (hash re-verified), no prior results regenerated or
overwritten.

**Isolation disclosure:** Docker is **unavailable** in this sandbox
(no binary, no sudo). All candidate-derived execution (prisma
validate/db-push on candidate schemas; bun execution of candidate
invariant code; SQLite behavior tests) ran inside fresh
`unshare -Urn` user+network namespaces with CPU/wall limits and
scratch directories — the Session-031/033 `ARCHAGENT_LOCAL_EVAL`
disclosed local-eval precedent, strengthened with namespaces. Trusted
harness code (gate runners, this session's Python) ran on the host.
No candidate byte executed unsandboxed.

## 2. Phase 1 — independent replay of the 22-candidate queue

Every queue reference was resolved from its archived generation JSON,
sha256-verified against both the generation record and the acceptance
ledger, content-screened (blank/secret/echo/placeholder), and
re-verified from scratch with **more depth than the in-loop gates
ever had**:

| Layer | prisma-model (19) | invariant (3) |
| --- | --- | --- |
| hash chain | 19/19 | 3/3 |
| frozen-contract structural gate | 19/19 | 3/3 |
| `prisma validate` | 19/19 | n/a |
| `prisma db push` → fresh SQLite | 19/19 | n/a |
| SQLite relation behavior (R1–R4, D1) | 19/19 | n/a |
| case table + 400-case seeded type-aware fuzz vs reference oracle | n/a | 3/3 |

**Result: 22/22 INDEPENDENTLY_VERIFIED, 0 quarantined.**
Sanitized manifest: `experiments/z038a-independent-retest/training-candidates.json`
(hashes/paths only, `training_eligible: 0`); dataset card:
`experiments/z038a-independent-retest/DATASET_CARD.md`.

### 2.1 Evaluator-integrity disclosures (test-layer defects, fixed pre-publication)

The first replay draft quarantined 7 candidates. **All 7 were defects
in my new test layer, not candidate defects** — fixed before any
verdict was published, both runs archived
(`replay-results-run1-evaluator-draft.jsonl` vs `replay-results.jsonl`):

1. R4 assumed RESTRICT for all non-cascade relations; Prisma optional
   relations default to **SetNull**. Fixed: optional→SetNull,
   required→Restrict, cascade→cascade.
2. Required-column filling wrote `'x'` into OTHER foreign keys
   (spurious constraint failures on the two-relation task). Fixed:
   valid parent rows inserted for every related parent.
3. Unquoted INSERT identifiers broke on the reserved word `limit`
   (pricing domain). Fixed: all identifiers quoted.

**Negative controls** (verifier must reject bad code): wrong-FK
schema rejected; boundary-violating invariant (`>` vs `>=`) rejected;
spec-required FK made optional rejected by R2 **even though prisma
validate passes it** — the behavior layer catches what the structural
layer cannot.

### 2.2 Data-qualification findings

- **Deduplication:** 22 unique outputs → **12 normalized structures**
  → **7 task families** (parent-1tm ×10, child-required-FK ×7,
  optional-FK ×1, self ×1, invariants ×3). 10/22 are the same
  parent-side pattern in different vocabulary.
- **Zero** route handlers, type interfaces, hooks/components/pages,
  multi-relation children, or real cascade semantics survive in the
  verified set.
- **Curriculum defect found:** the 037 `rel-cascade` level ("TRANSFER:
  cascade deletion") never specified `onDelete: Cascade` in spec,
  demo, or gate — its verified candidates are plain required-FK
  relations. Training on them teaches FK shape, not cascade.
- **Provenance:** all 22 resolve to model-harness generation
  directories (teacher bytes never entered them); the two challenge
  pieces are additionally confirmed model-origin by the 037
  attribution.json.

## 3. Phase 2 — fresh-suite retest of the "invariant-cap correction"

### 3.1 Archive forensics first: the 037 attribution was wrong

Before building the retest, the 037 invariant-loss exhibits were
re-examined directly:

- **Track C's clean re-run generated a COMPLETE, gate-passing,
  behaviorally-correct 251-char `ap-transition` predicate at step 0**
  (tokens: 200/200 — the generation cap, but the text is complete and
  syntactically closed). The in-loop probe recorded
  `{"pass": false, "counterexample": ""}` and the piece was
  probe-rejected, never installed, and final-scored "file missing".
  Re-probing that exact archived candidate with both the 037 probe
  (reproduced) and this session's fresh probe: **PASSES**.
  Root cause: the probes-disabled monkeypatch returns
  `{"pass": None}` and the 037 controller computed
  `bool(None) == False` — **a harness defect threw away a solved
  piece**, not a token-cap truncation.
- **The 037 invariant probe emits TWO verdict lines when the property
  fuzz fails** (false, then an unconditional true; the runner takes
  the last line) — fuzz enforcement was silently masked in EVERY 037
  run (over-acceptance direction). This is why 037's "fuzz" never
  caught anything.
- Track D's clean re-run failures were genuine generation-shape
  failures (prompt-echo loops at those seeds).

### 3.2 The retest design

- **New frozen suite** (`archagent/z038a/suite.py`): orchard / marina
  / bakery — domains disjoint from every prior suite, curriculum, and
  demo vocabulary; 15 pieces (6 prisma, 3 invariants covering the
  state-transition / interval-overlap / numeric-bound classes, 6
  routes covering GET-search + POST-validation). Suite sha256
  `ffff91b557c3032c42effff45dbd26cfa963db1f20ba0625db52bab29c3d7f07`
  recorded in `suite/MANIFEST.json` **before any generation**; the
  runner refuses to run on drift.
- **Repair package (declared, total budget unchanged at 2000
  tokens / 6 attempts per piece for BOTH tracks):**
  P1 tri-state probe semantics (None ≠ False; harness-class defects
  never reject); P2 seeded, type-aware, single-verdict in-loop
  invariant probe; P3 invariant cap 200→300 (within the same total);
  P4 mechanical prompt-echo stripping (raw outputs archived).
- **Track B** = the exact 036 baseline treatment (blind ladder,
  520-token cap, structural-only in-loop). **Track R** = the 037
  engine forked with P1–P4. Same checkpoint, **same per-piece seeds**,
  same contracts, same box, sequential single-loaded model.
- Per track AND domain: schema, invariant files, route files, probe
  DBs reset (037's contamination lesson). Live route probes with
  **no-verdict ≠ pass** in final scoring.
- Disclosed staging fix (found in the smoke run): the prisma client
  is regenerated after the prisma pieces and before route pieces —
  in-loop route probes otherwise run against a stale client
  (seeding TypeError). 037 never hit this because its in-loop route
  probes uniformly returned no-verdict (pre-fix template bug).

### 3.3 Results

| | Track B (baseline) | Track R (repaired engine) |
| --- | --- | --- |
| **Final score** | **9/15** | **8/15** |
| Loop tokens | 15,272 | 13,862 (−9%) |
| Wall time | 1,985 s | 1,971 s |
| Peak RSS | 2,628,496 KiB (both; model-dominated) | |

Paired: 13/15 concordant, **1 discordant** (`ma-booking`, B wins);
McNemar exact p = 1.0 — **no significant difference; the ≥20%
improvement target is NOT met** (R is −7% relative).

Per family:

| family | B | R |
| --- | --- | --- |
| relations-parent (3) | 3 | 3 |
| relations-child (2) | 3* | 3* |
| relations-child-optional (1) | 1 | **0** |
| invariant-state (1) | 0 | 0 |
| invariant-interval (1) | 1 | 1 |
| invariant-numeric (1) | 1 | 1 |
| route-get (3) | 1 | 1 |
| route-post (3) | 0 | 0 |

\* includes the optional-FK child.

- **The invariant-cap hypothesis is REFUTED:** both tracks resolve
  2/3 invariants on attempt 1 using **27–70 tokens** — nowhere near
  any cap. The 037 invariant losses were substantially harness
  artifacts (§3.1), and on a clean verification stack the 0.5B model
  generates these invariant shapes reliably, including
  interval-overlap (the hardest 036/037 class).
- The one failing invariant (`or-stage`) fails **identically in both
  tracks**: the model writes the demo's domain words
  (`raw→edited→published`) instead of the task's
  (`growing→ripe→picked`); the behavioral probe correctly rejects it,
  the counterexample feedback cannot fix it (dedup spiral). A real,
  well-characterized model gap: demo-vocabulary copying.
- **R's single loss (`ma-booking`)** is a near-miss prisma piece
  (FK optional ✓ but relation-side `Berth` missing `?`) that the
  micro-repair FIM loop could not fix (13-token duplicates → flat →
  stop at 917/2000 tokens) while B's blind 520-token resampling hit
  the correct form on attempt 4 (2,080 tokens). The engine's
  conservative stop rules lost the piece; its known FIM limitation
  ("cannot rewrite optionality") is confirmed.
- **Routes remain the universal gap: 1/12 across both tracks**
  (only `or-get`). Consistent with 037's finding (GET search-filter
  0/4 tracks; POST multi-branch 1/6 there).
- B reproduced its 037 four-track score exactly (9/15) on a fresh
  suite with the same treatment — the baseline is stable.

## 4. Phase 3 — proposed (NOT executed) training plans

See `docs/ZAI_SESSION038A_TRAINING_PLANS.md`. Summary:

- **Plan 1 (LoRA pipeline pilot on the 22 verified model-origin
  examples):** CPU-feasible (~2 GiB, <1 h, 440 steps); success
  criterion is pipeline validation, never a capability claim.
- **Plan 2 (teacher distillation):** 3 pure-teacher + 1 hybrid
  challenge pieces exist, covering exactly the never-solved families
  (GET/POST routes); a real run needs 50–200 authored pieces.
- **Plan 3 (preference pairs):** **measured blocker — the archives
  contain ZERO same-prompt (chosen, rejected) pairs**; only 5
  cross-prompt pairable tasks. A dedicated K=8-per-task sampling run
  (~1.7 h) must precede any DPO.
- **Holdout policy:** the z038a suite becomes the dev benchmark
  (baselines recorded); a new domain-disjoint holdout must be frozen
  before hyperparameter selection for any trained variant.

## 5. Deliverables index

| Artifact | Path |
| --- | --- |
| This report | `docs/ZAI_SESSION038A_INDEPENDENT_RETEST.md` |
| Training plans | `docs/ZAI_SESSION038A_TRAINING_PLANS.md` |
| Replay code | `archagent/finetune/replay.py`, `replay_manifest.py` |
| Retest code | `archagent/z038a/suite.py`, `retest.py` |
| Per-candidate replay results | `experiments/z038a-independent-retest/replay-results.jsonl` (+ `-run1-evaluator-draft.jsonl`) |
| Sanitized manifest | `experiments/z038a-independent-retest/training-candidates.json` |
| Dataset card | `experiments/z038a-independent-retest/DATASET_CARD.md` |
| Frozen suite + hash (pre-generation) | `experiments/z038a-independent-retest/suite/{MANIFEST.json, suite.json}` |
| Retest summaries + ledgers + generations | `experiments/z038a-independent-retest/retest/{summary-B.json, summary-R.json, B/, R/}` |
| Paired analysis | `experiments/z038a-independent-retest/retest/paired-analysis.json` |
| Session state | `SESSION038A_STATE.json` |

### Reproduction commands

```bash
# Phase 0
python -m unittest tests.test_finetune_audit tests.test_candidate_queue -v
python -m archagent.finetune.audit_archives --repo . \
  --out experiments/finetune-readiness-038/archive-audit.json
python -m archagent.finetune.candidate_queue --repo . \
  --out experiments/finetune-readiness-038/candidate-queue.jsonl \
  --summary experiments/finetune-readiness-038/queue-summary.json
node --test archagent/verify/adversarial.test.mjs   # 30/30

# Phase 1 (needs bun + prisma in /home/z/my-project, model at
# ARCHAGENT_MODEL_DIR for nothing — replay runs no model)
python -m archagent.finetune.replay
python -m archagent.finetune.replay_manifest

# Phase 2 (needs the frozen model)
ARCHAGENT_MODEL_DIR=/home/z/models/qwen25-coder-05b \
  python -m archagent.z038a.retest
python -m archagent.z038a.suite   # manifest drift check
```

Dependency pins: python 3.12.16, torch 2.15.0+cpu,
transformers 4.57.6, node v24.22.2, bun (prisma CLI from
`/home/z/my-project/node_modules`), model safetensors sha256
`aff8914e…a47f80`.

## 6. Failure taxonomy (fresh suite, both tracks)

| Class | Pieces | Evidence |
| --- | --- | --- |
| Route POST multi-branch validation | or-post, ma-post, ba-post (both tracks) | parse-rejects / clause-rejects; never a complete validated handler |
| Route GET search-filter | ma-get, ba-get (both) | clause-rejects (`where` construction, include, ordering) |
| Demo-vocabulary copying | or-stage (both) | complete predicate with the DEMO's states; probe-rejected with counterexample; feedback loop dedup-spins |
| Relation-side optionality near-miss | ma-booking (R) | `berthId String?` ✓ but `berth Berth` missing `?`; FIM micro-repair cannot rewrite it |
| Generation degeneracy | various rejects | prompt-echo lines, near-empty decompose outputs (P4 strip mitigates echo; degeneracy persists at some seeds) |

## 7. Resource accounting

- Phase 1 replay: 22 candidates, 52.6 s wall (excl. model — no
  inference), all inside namespaces.
- Phase 2 retest: B 1,985 s / R 1,971 s wall; loop tokens 15,272 /
  13,862; peak RSS 2,628,496 KiB (≈2.6 GiB, model-dominated; both
  tracks identical).
- Model: loaded once per track-run process; 0.5B params; no GPU.

## 8. Go/no-go for separately-authorized fine-tuning

**Conditional GO — Plan 1 (LoRA pipeline pilot) only** (22 verified
model-origin examples, hash-chained, family-labeled; CPU-feasible;
pipeline-validation goal). **NO-GO for capability claims** from 22
examples; **NO-GO for DPO** until a same-prompt pair-collection run
exists (measured: zero pairs in archives); teacher distillation only
after the pilot. Any GPU rental requires separate budget approval.
The scientific question — whether Qwen's *future generalization*
improves — remains open: this session's evidence says the 037
"invariant gap" was largely an evaluator artifact, while the *real*
gaps (routes, demo-copying, relation-side optionality near-misses)
are the families any future training run must target and any future
evaluation must measure behaviorally.

## 9. Negative findings (honesty section)

1. The repaired engine did **not** beat the baseline (8/15 vs 9/15,
   p=1.0). The ≥20% target failed again.
2. The 037 final report's "token-cap truncation" explanation for its
   invariant losses is **wrong in the decisive case** (Track C): a
   correct, complete, gate-passed predicate was discarded by a
   `bool(None)` harness defect. This session's forensics + fresh-suite
   result supersede that attribution.
3. 037's invariant "fuzz" never enforced anything (double-emit
   masking) — every 037 behavioral invariant verdict was case-table
   only, in-loop and in final scoring alike.
4. The verified training corpus is small (22), heavily duplicated
   (12 structures), and skewed to simple relation patterns; it
   contains none of the families where the model actually fails.
5. Zero same-prompt preference pairs exist in all 037 archives.
