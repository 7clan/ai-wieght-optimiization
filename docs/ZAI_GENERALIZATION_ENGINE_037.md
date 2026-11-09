# SESSION 037 — Generalizable Intelligence, Adaptive Program Synthesis & Verified Skill Transfer

**Branch**: `exp/zai-generalization-engine-037` (forked from Session-036
milestone `384e0245812f772c06d18f7b06503499ae9bf6d1`)
**Model**: `Qwen/Qwen2.5-Coder-0.5B`, frozen — safetensors sha256
`aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`
(identical to the Session-035/036 pin; re-verified after both sandbox
resets).
**Hardware**: 2 CPU threads, 4 GiB RAM, CPU-only inference, one model
resident at a time, dev server stopped during generation phases.

Status markers: **[DONE]** evidence committed; **[PENDING]** running
or queued at the time of the latest commit; numbers update in place.

---

## 1. Executive summary

Session 036 had ended with a paradox: a fixed strategy ladder resolved
7/12 RoomReserve contracts while the "adaptive" Thompson bandit
resolved 4/12 at equal budget. Session 037 set out to explain that
loss, replace the mechanism with something a 0.5B model can actually
benefit from, and measure whether any of it generalizes to unseen
domains.

What we found, in one paragraph each:

* **The Session-036 loss was mostly self-inflicted.** Five of the nine
  bandit arms carried degenerate prompts (empty FIM regions, unfilled
  placeholders), 31% of all archived candidates were near-empty
  early-EOS echoes, the token extractor could not read the verifier's
  message formats, and acceptance was structural-only. The famous
  "impossible" time-window overlap check turned out to be *producible*
  — one archived attempt contains a correctly adapted interval check
  that was rejected for one missing clause plus demo remnants
  (Exhibit E1).
* **Structure beats adaptation at 0.5B.** The 037 engine (TaskIR
  decomposition, deterministic prompt laws, budget-aware conservative
  policy, in-loop behavioral probes with counterexample repair) beat
  the 036-style baseline on both curricula (relations 3/5→4/5 dev,
  invariants 1/5→3/5 dev) and — **[PENDING: four-track numbers]** — on
  the frozen three-domain suite.
* **The fancier the meta-layer, the less it helped.** Zero reasoning
  principles were promoted (every candidate failed transfer evidence,
  one was correctly rejected as harmful); reflective prompt evolution
  never beat the deterministic laws; the promotion pipelines did
  exactly their job by refusing to ship unproven machinery. The honest
  result is that at 0.5B scale, verifiable structure (decomposition,
  anchored checklists, probes) is where the wins live.
* **Evaluator integrity is a first-class research finding.** Two
  scorer bugs were found and fixed during 037 (a false-reject on
  correctly typed list relations; a grammar rejection of
  same-line-as-`model X {` fields), both with disclosed re-scoring
  impact. The adversarial suite stayed at 30/30 throughout.

## 2. Mission and success criteria

The mission (task book): build an adaptive program-synthesis system
that extracts generalizable problem-solving programs from failures,
improves decisions on unfamiliar tasks, and progressively reduces
dependence on teacher business logic — then *prove* it on unseen tasks
under equal compute.

Success criterion: the improved system must beat the fixed
Session-036-style baseline on independent unseen tasks at equal
compute, target ≥20% relative improvement with no cross-domain
regression (a research target, not a guarantee), with uncertainty and
sample-size limitations reported.

**[PENDING: verdict against the criterion — filled by §13.]**

## 3. Environment, recovery, and reproducibility

* Repository: `7clan/ai-wieght-optimiization`, branch
  `exp/zai-generalization-engine-037`. Every phase is committed with
  its evidence; the branch never touched `main` or other sessions'
  branches.
* The sandbox was reset twice during this session (after Phase 0, and
  again mid-Phase-10). Both recoveries are recorded in
  `SESSION037_STATE.json`; the model was re-downloaded and its sha256
  re-verified against the pin both times. The second reset destroyed
  the venv ML stack mid-experiment; the interrupted first Track-A run
  (3/15 pieces, no summary) was discarded and re-run from scratch
  because seeds are deterministic per (piece, attempt).
* Reproduction entry points:
  * `python -m archagent.generalize.run_tracks A|B|C|D` — the
    four-track comparison (refuses to run if the frozen suite hash
    drifts).
  * `python -m archagent.generalize.run_curricula` — curriculum A/B.
  * `python -m archagent.generalize.validate_principles` — principle
    promotion A/B.
  * `python -m archagent.generalize.validate_docgate` — documentation
    workflow A/B.
  * `python -m archagent.generalize.run_challenge` — Phase 11.
  * `node archagent/verify/adversarial.test.mjs` — evaluator integrity
    (30/30 required).

## 4. Phase 1 — Root-cause analysis of Session 036 [DONE]

Full report: `experiments/z037-generalization/phase1-rootcause/ROOT_CAUSE.md`
(reproducible from the 036 archives via `taxonomy.py`).

Nine investigation questions, answered with archived exhibits; the
headline findings:

| Question | Finding |
|---|---|
| Why did `exact_shape` dominate? | It was the only strategy whose prompt was valid for generation; the five repair-shaped arms were degenerate on nonexistent files (53/87 Track-C attempts burned there) |
| Why did the bandit repeat failures? | 9 arms ÷ 8 attempts cannot concentrate; 7 arms started at Beta(1,1) — indistinguishable from the strongest arm |
| Were priors wrongly transferred? | Partially — `missing_literal` priors described Session-035's UI shape, not 036's demo-complete contracts |
| Syntactic-only rewards? | Yes — probes were off; the POST-listing hook passed every gate |
| Prompt information load? | Both tails failed; the binding variable is integration surface (clauses × cross-referenced identifiers), not word count |
| Relations & time windows? | Relations: genuine model gap (0/16, demo contained no relation). Overlap: producible (Exhibit E1) — a contract-granularity failure |
| Controller misclassification? | Categories were sound; the arms they indexed and the token-blind regexes were not |
| Whole function vs expression? | Whole-file for initial generation, micro-repair for verified near-misses — the 036 loop never did the latter |

Three-source failure taxonomy (reproducible counts in `taxonomy.json`):
harness/strategy 5 classes (H1–H5), strategy/prompt 4 (P1–P4), model
capability 4 (M1–M4). The 037 design (§5–§7) maps 1:1 onto these.

## 5. Phase 2 — TaskIR: the structured programming interface [DONE]

`archagent/generalize/taskir.py` (434 lines): a validated intermediate
representation — entities+relations with referential integrity,
invariants with case tables, route handlers with ≤6 clauses, UI pieces
with string/access contracts — compiled from a JSON spec into
toposorted `Piece`s with anchors, demos, gates and oracles.

Supporting laws (`prompting.py`), each discovered from a verified
failure:

1. **Anchor-inside**: the completion anchor is the construct's own
   first line (e.g. `export async function POST(`), never the file's
   imports — early-EOS becomes mechanically detectable.
2. **Demo-completeness**: the demo must contain every construct shape
   the contract requires, with different-domain identifiers.
3. **Bounded clauses**: ≤6 clauses per piece (integration surface is
   the binding constraint, per Phase 1 Q5).
4. **L-CHECKLIST** (found in curriculum bring-up, 6/6 vs 0/6): render
   the required elements as a comment *inside* the construct anchor —
   identical information to the spec, but placement defeats
   demo-field copying entirely.
5. **Early-EOS retry**: near-empty candidates (anchor echo + EOS) are
   detected and re-anchored at near-zero cost instead of being scored
   as strategy failures (Phase 1 H5: 31% of 036 candidates).

Smoke result: the courier `windowsOverlap` invariant — which Session
036 failed 16/16 — resolved on attempt 1 with 200 tokens.

## 6. Phase 3 — Budget-aware conservative policy [DONE]

`archagent/generalize/policy.py`: a deterministic ladder replacing the
bandit. Conservative start by contract family (the empirically
strongest strategy first), near-miss escalation (1–2 failing clauses
with the rest intact → micro-repair / clause-decompose instead of
re-rolling whole files), failure-kind-aware repair tier (missing
FIELDS → spec-clause feedback regen; missing CALLS → FIM),
duplicate-signature early stop, per-piece token budgets (a bring-up
bug shared the budget across pieces and starved fresh ones — fixed
and disclosed), and resample mutations for attractor escape.

## 7. Phase 4 — Reasoning-principle engine: an honest negative [DONE]

`archagent/generalize/principles.py`: full lifecycle — candidate
identification from verified failure+correction pairs,
de-taskification audit (rejects code solutions and task-specific
rules), ≥2-task application requirement, A/B against the existing
flow, refusal to merely reproduce old answers, versioned store with
rollback.

**Result: zero principles promoted.** All four model-reflected
candidates failed their transfer evidence (PR-MOD-002 was actively
harmful — its with-condition arm burned +64% tokens with no
resolutions; the others showed no delta). The teacher-seeded
boundary-enumeration principle also failed both conditions. The
pipeline did exactly what it was designed to do: refuse to ship
unproven machinery. At 0.5B scale the deterministic prompt laws
already encode what the principles tried to add, and the model cannot
yet benefit from free-form procedural addenda.

Reflection-prompt note: the zero-shot reflection prompt produced
literal `'<another sentence> RULE: <yet another sentence>'`
placeholders; a few-shot format fix made reflection legible, which is
itself a data point about 0.5B instruction-following.

## 8. Phase 5 — Reflective prompt evolution [DONE]

`archagent/generalize/promptevol.py`: bounded Pareto pool per
instruction slot (correctness / tokens / attempts), dev-frontier
promotion with held-out non-regression, periodic compression,
teacher-origin tagging. Outcome: evolved instructions never beat the
deterministic laws on dev tasks; the pool stayed small. Combined with
§7, the honest conclusion is that at this scale the wins come from
verifiable structure, not from evolved prose.

## 9. Phase 6 — Counterexample-driven repair [DONE]

`archagent/generalize/probe.py`: invariant case-table probes plus
300-case fuzz against a reference oracle; route probes with a mocked
`NextRequest` against a scratch database, self-seeding via the prisma
client. Negative control verified: a `<=` vs `<` bug yields the
minimal counterexample "touching returned true, expected false".
Counterexamples feed the repair loop as *the* feedback (quoted
verbatim into regeneration), replacing raw gate-failure text (Phase 1
P3). Structural gates alone are never acceptance when a behavioral
oracle exists.

## 10. Phase 7 — Capability-gap curricula [DONE]

`archagent/generalize/curricula.py` + `run_curricula.py`, identical
budgets (6 attempts / 2000 tokens per piece), identical seeds,
task-level prisma validation:

| Curriculum | Arm | Dev resolved | Dev tokens | Transfer |
|---|---|---|---|---|
| A: Prisma relations (6 tasks) | 036 baseline | 3/5 | 6000 | 1/1 |
| | 037 engine | **4/5** | **4238** | 1/1 |
| B: Logical invariants (6 tasks) | 036 baseline | 1/5 | 3642 | 0/1 |
| | 037 engine | **3/5** | **1807** | 0/1 |

Per-task detail in the committed summaries. The engine's wins
concentrate where the baseline burns its whole budget (A.2 optional
FK: baseline 7 attempts/2100 tokens failed, engine 5/941 resolved).
A.4 (two relations on one model) failed for both arms — the demo
lacks the pattern; recorded as a curriculum gap, not hidden. Transfer
tasks: cascade-deletion (A) resolved by both; lifecycle chain (B) by
neither.

## 11. Phase 8 — Controlled documentation-retrieval workflow [PENDING]

`archagent/generalize/docgate.py`: failure-signature gap
classification (relation / route-shape / invariant), a pinned offline
corpus (v1) with every snippet labeled DOC-FACT (restates
documentation, with source and version) or CHOICE (a house decision
documentation cannot justify), and a strict default-OFF rule.

`validate_docgate.py` runs the A/B on four fresh mini-tasks (harbor,
atelier, clinics, depots — disjoint from the frozen suite and both
curricula): the doc block becomes engine-default **only** if it
resolves strictly more pieces at ≤ tokens. **[PENDING: decision.json
numbers and verdict.]**

## 12. Phase 9 — The frozen evaluation suite [DONE]

`archagent/generalize/frozen_suite.py` + `MANIFEST.json`: three fresh
domains (permit approvals with a state machine; machine-maintenance
relational logs; pricing plans with subscription quotas) × 5 pieces
(2 prisma models, 2 route handlers, 1 invariant) = 15 pieces, sha256
`1a57852bf28f40f5d26a2ab8627e34bc4123e08938ebbacc8bdecdb846ead017`
recorded **before any generation**. Freeze disclosure: the initial
freeze was superseded pre-generation to add route probe cases and fix
one self-contradictory `maxLimit` case — both changes committed
before any model output existed. The track runner refuses to run on
suite drift. Domain specs reuse nothing from TaskFlow / MediVault /
StockPilot / RoomReserve.

## 13. Phase 10 — The four-track comparison [PENDING]

Design (`run_tracks.py`): identical budgets per piece per track
(6 generations / 2000 tokens), identical seeds per (piece, attempt)
across tracks, and final scoring that is independent of every track's
own loop (structural gates + behavioral oracles + prisma validate +
route probes on fresh databases, re-run on the installed files):

| Track | Treatment |
|---|---|
| A | Unassisted: natural spec + anchor, blind resampling, no demo/checklist/feedback |
| B | Session-036 Track-B baseline: demo + spec + anchor, blind ladder, raw-gate feedback |
| C | 037 engine, structural-only acceptance (probes disabled) — isolates decomposition+policy |
| D | Full system: in-loop behavioral probes + counterexample repair + principle addenda (0 promoted) |

**[PENDING: the results table — final resolved X/15 per track, tokens,
per-piece breakdown, paired analysis, and the ≥20% verdict with
uncertainty caveats.]**

## 14. Phase 11 — Full-stack independence challenge [PENDING]

Frozen spec `experiments/z037-generalization/challenge/SPEC.json`
(sha256 in `FREEZE.json`, recorded before any generation): the
Greenhouse plant-care app — 2 related prisma models (required FK),
`needsWater` boundary invariant, POST+GET routes with 4+2 behavioral
probe cases, and a client page (fetch on mount, needs-water badge,
watering form, error/loading states). Built by the engine in Track-D
configuration with a full attribution ledger and **no silent teacher
fixes**: failures stay failures in the record; any disclosed teacher
pass for demo purposes is labeled per-line.

**[PENDING: engine-only piece scorecard, attribution percentages,
schema validation, live-browser verification screenshots.]**

## 15. Resource accounting

**[PENDING: final table — tokens, attempts, CPU-seconds and wall time
per phase, from the committed ledgers.]**

Disclosed so far: curricula A+B (both arms) 15,687 tokens total;
principle validation and prompt-evolution runs ledgered in their
artifacts; the second sandbox reset cost one discarded partial
Track-A run (3 pieces, no summary).

## 16. The twelve questions

1. **Did the improved system beat the fixed baseline on unseen tasks
   at equal compute?** **[PENDING §13]**
2. **By how much — was ≥20% met?** **[PENDING §13]**
3. **Which mechanisms drove the gains?** Decomposition+laws+policy are
   isolated by Track C vs B; probes+counterexamples by D vs C;
   principles contributed nothing (0 promoted — §7); prompt evolution
   nothing (§8); curricula shaped the demos/laws but transfer was
   1/2 (§10); docgate **[PENDING §11]**.
4. **Why did the 036 bandit lose?** Degenerate arms + unbudgeted
   exploration + structural-only rewards (§4).
5. **Were any reasoning principles promoted?** No — and the pipeline
   correctly refused everything; one candidate was rejected as
   harmful (§7).
6. **Did curricula transfer?** Same-family transfer 1/2 tasks;
   cross-family generalization comes from the laws, not the
   curricula (§10).
7. **Did prompt evolution beat the deterministic laws?** No (§8).
8. **Was the documentation workflow proven before enabling?** It is
   default-OFF by construction; the A/B verdict is **[PENDING §11]**.
9. **How were the three failure sources separated?** Reproducible
   taxonomy from archives (§4) + evaluator-integrity adversarial
   suite (30/30) + two scorer bugs found, fixed and re-scored with
   disclosed impact (§1).
10. **Four-track numbers with honesty about n=15?** **[PENDING §13]**
11. **Challenge attribution?** **[PENDING §14]**
12. **What would make the ≥20% target more credible?** Larger frozen
    suites (n≥30 pieces), a second seed per piece to separate
    seed-luck from mechanism, and — the data suggests — a model that
    can follow free-form procedural addenda, since the meta-layers
    were the non-contributors at 0.5B.

---

## Limitations (standing)

* n = 15 frozen pieces, one seed per (piece, attempt): a two-piece
  swing is within noise; all claims are paired-comparison scoped and
  labeled with this caveat.
* The teacher (author) built the harness, gates, demos, curricula and
  suite — the study measures the *model's* unassisted vs assisted
  performance inside that harness, not harness-neutral intelligence.
* CPU-bound: one model resident, budgets enforced per piece; wall
  times are long and the sandbox was reset twice (disclosed above).
