# SESSION038A Dataset Card — Independently Verified Training Candidates

**Status:** verification only. **No training occurred, no gradients were
computed, no adapter exists.** `training_eligible` remains `0` for every
entry; graduation to `ELIGIBLE` requires explicit user authorization of
a separate training branch (see `docs/SESSION038_READINESS.md`).

## Source

- 22 in-loop accepted outputs of the frozen `Qwen/Qwen2.5-Coder-0.5B`
  (safetensors sha256
  `aff8914e…a47f80`, identical to the Session-035/036/037 pin),
  selected by the Session-038 preparation queue
  (`experiments/finetune-readiness-038/candidate-queue.jsonl`, 30
  reported acceptances − 8 duplicate outputs − 2 contaminated-ledger
  rows → 22 traceable unique outputs).
- Provenance chain re-derived this session: candidate bytes resolve
  from archived generation JSONs, sha256-verified against both the
  generation record and the acceptance ledger; every record sits in a
  `gen`/`engine-gen` directory written by the model harness. Teacher
  bytes never enter those directories; the two challenge pieces are
  additionally confirmed model-origin by the Session-037
  `attribution.json`.

## Independent verification (this session)

Each candidate was re-verified from scratch, under `unshare -Urn`
user+network-namespace isolation (Docker is unavailable in this
sandbox; disclosed, per the Session-031/033 `ARCHAGENT_LOCAL_EVAL`
precedent):

| Layer | prisma-model (19) | invariant (3) |
| --- | --- | --- |
| hash chain vs queue + ledger | 19/19 | 3/3 |
| content flags (blank/secret/echo/placeholder) | 0 flagged | 0 flagged |
| frozen-contract structural gate (`run_gates.mjs`) | 19/19 | 3/3 |
| `prisma validate` | 19/19 | n/a |
| `prisma db push` to fresh SQLite | 19/19 | n/a |
| SQLite relation behavior (R1 valid-FK, R2 null-FK vs spec optionality, R3 bogus-FK, R4 restrict/setnull/cascade, D1 column default) | 19/19 | n/a |
| case table + 400-case seeded type-aware fuzz vs independent reference oracle | n/a | 3/3 |

**Result: 22/22 INDEPENDENTLY_VERIFIED, 0 quarantined.**

Negative controls proved the verifier discriminates: a wrong-FK
schema, a boundary-violating invariant (`>` instead of `>=`), and an
optional-FK schema where the spec requires a required FK were all
rejected.

### Evaluator integrity disclosure

The first replay draft misclassified 7 candidates as behaviorally
failing. Root causes were **three defects in the new test layer**, not
candidate defects, and were fixed before any verdict was published
(both runs archived):

1. R4 assumed RESTRICT for every non-cascade relation; Prisma optional
   relations default to SetNull. Fixed: optional→SetNull,
   required→Restrict, declared cascade→cascade.
2. Required-column filling wrote placeholder `'x'` into OTHER foreign
   keys (spurious constraint failures on the two-relation task).
   Fixed: valid parent rows are inserted for every related parent.
3. Unquoted INSERT column lists broke on the reserved word `limit`
   (pricing domain). Fixed: all identifiers quoted.

Draft run: `replay-results-run1-evaluator-draft.jsonl` (7 spurious
quarantines). Final run: `replay-results.jsonl` (22/22).

## Composition (deduplication)

- 22 unique outputs → **12 distinct normalized structures**
  (models/fields/functions renamed to placeholders; see
  `model_fingerprint`/`invariant_fingerprint`).
- → **7 task families**:

| family | pieces |
| --- | --- |
| relations-parent-1tm | 10 |
| relations-child-required-fk | 7 |
| relations-child-optional-fk | 1 |
| relations-self | 1 |
| invariant-numeric-boundary | 1 |
| invariant-capacity | 1 |
| invariant-duplicate-detection | 1 |

Known concentration: 10 of 22 pieces are the same parent-side
one-to-many pattern in different vocabulary; the required-FK child
pattern contributes 7 more. **Zero route handlers, zero type
interfaces, zero hooks/components/pages, zero multi-relation children,
and no real cascade-deletion semantics** (see the curriculum finding
below) survive in the verified set — the exact families the
Session-037 four-track found universally hard.

## Negative findings (data-qualification relevant)

1. **rel-cascade label vs spec gap:** the Session-037 curriculum level
   `rel-cascade` ("TRANSFER: cascade deletion") never asked for
   `onDelete: Cascade` in its spec, demo, or gate; the verified
   candidates correctly implement plain required-FK relations. Any
   future training on these examples teaches FK shape, **not** cascade
   semantics.
2. **Structural saturation:** for parent-side pieces the archived
    candidates are normalized-code duplicates across domains
    (Band/Screen/Approver/Machine/Plan/Plot/Coupon/Aisle collapse to 2
    structures). Family-weighted sampling is mandatory to avoid
    10× over-weighting the parent-side pattern.
3. **Token cost:** verified examples cost 18–300 generated tokens each
    (single model block or single function). Total ≈ 3.4k generated
    tokens of verified model-origin signal.

## Contamination & licensing

- Evaluation-suite pieces in this set (ap/mn/pr from the frozen
  Session-037 suite, gh from the frozen challenge spec) were verified
  against specs whose file hashes match their freeze records
  (re-verified this session). If any future training run uses these
  examples, the Session-037 suite is **consumed** for that model line;
  a new domain-disjoint holdout must be frozen first (planned in the
  Phase-3 proposals).
- All candidate bytes are model-generated from task specifications
  written by the research harness; no third-party copyrighted code is
  included. Prompts/candidates stay in the repo archives, referenced
  by sha256 only.

## Files

- `experiments/z038a-independent-retest/replay-results.jsonl` —
  per-candidate verification layers, fingerprints, duplicate links.
- `experiments/z038a-independent-retest/replay-summary.json` — run
  stats + isolation disclosure.
- `experiments/z038a-independent-retest/training-candidates.json` —
  sanitized manifest (this card's machine-readable counterpart).
- `archagent/finetune/replay.py`, `replay_manifest.py` — reproduction:
  `python -m archagent.finetune.replay && python -m
  archagent.finetune.replay_manifest`.
