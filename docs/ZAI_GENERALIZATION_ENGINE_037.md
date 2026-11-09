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
* **Structure beats adaptation at 0.5B — on schemas, not on final
  count.** The 037 engine (TaskIR decomposition, deterministic prompt
  laws, budget-aware conservative policy, in-loop behavioral probes
  with counterexample repair) beat the 036-style baseline on both
  curricula (relations 3/5→4/5 dev, invariants 1/5→3/5 dev) but
  LOST the frozen-suite four-track: **A 4/15, B (036 baseline) 9/15,
  C (engine structural) 6/15, D (engine full) 6/15** — D is −33%
  vs B at equal budget. The engine closed the 036 relation gap
  completely (6/6 prisma models, schema validates in all domains,
  ⅓ the tokens) but lost every invariant to a token-cap truncation
  exhibit (the model produced a correct 3-branch predicate twice and
  was cut at the 200-token invariant cap) and shared the baseline's
  universal route gaps.
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

**Verdict: FAILED.** D vs B on the frozen suite: 6/15 vs 9/15 = −33%
relative at equal per-piece budgets (D used ⅓ of B's tokens). The
engine won the schema-relation family outright (6/6 vs 5/6 models,
all-domain schema validity vs 1 domain invalid for B) but lost all
three invariants and matched the baseline's single route win. See §13
for the full decomposition and §16 for what would make the target
credible.

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

`validate_docgate.py` ran the A/B on four fresh mini-tasks (harbor,
atelier, clinics, depots — disjoint from the frozen suite and both
curricula): **without-doc 4/8 (5,144 tokens) vs with-doc 6/8 (4,885
tokens) → default-ON justified by the pre-registered rule.** The two
flipped pieces are exactly the Phase-10 universal gaps: dg-depot-get
(a GET search-filter route — 0/4 tracks) resolved only with the
pinned `searchParams` doc; dg-artwork (optional FK) likewise. This is
the only add-on layer that beat its absence (principles: 0 promoted;
prompt evolution: no wins). The doc block was wired into the
controller with exactly the measured semantics (retry-attempt
injection from prior failures) and used for the Phase-11 challenge —
the four-track configs were frozen without it, disclosed.

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

## 13. Phase 10 — The four-track comparison [DONE]

Design (`run_tracks.py`): identical budgets per piece per track
(6 generations / 2000 tokens), identical seeds per (piece, attempt)
across tracks, and final scoring that is independent of every track's
own loop (structural gates + behavioral oracles + prisma validate +
route probes on fresh databases, re-run on the installed files).

**Final corrected results** (after the contamination fix below):

| Track | Treatment | Final | Loop tokens | prisma (6) | invariants (3) | routes (6) |
|---|---|---|---|---|---|---|
| A | unassisted | 4/15 | 21,844 | 3 | 1 | 0 |
| B | 036 baseline | **9/15** | 20,170 | 5 | **3** | 1 |
| C | engine structural | 6/15 | 7,078 | **6** | 0 | 0 |
| D | engine full | 6/15 | 6,696 | **6** | 0 | 0 |

**D vs B: −33% relative — the ≥20% target failed.**

Per-piece paired decomposition (B vs D): B-only wins are the three
invariants (ap-transition, mn-window, pr-quota); D-only win is
ap-request (the relation model B failed). Both accept mn-post…
actually neither: see the contamination note. Universal failures
across all tracks: GET search-filter routes (0/4 tracks), POST
multi-branch validation routes (0/4 tracks in the corrected scoring).

**Why the engine lost the invariants — exhibits, not excuses:**

* `ap-transition`: the model produced a correct 3-branch predicate
  TWICE (attempts 0 and 4, archive `tracks/C-run1-contaminated/gen/
  ap-transition-exact_shape-0-*.json`) and both were TRUNCATED at
  251 chars by the engine's 200-token invariant cap — the baseline's
  520-token budget completed the same shape first-try. A harness
  parameterization bug (Phase-1 H3, micro-token starvation, in a new
  form), fixed for the record but NOT re-run against the frozen suite
  (post-hoc tuning risk; disclosed instead).
* `mn-window`: a forced-continuation attempt contains the correct
  interval check, then prompt-echo prose corrupted the extraction.
* `pr-quota`: placeholder stubs (`// ...`) — no logic ever appeared.

**Why C and D are identical (6/15, near-identical tokens):** the
failures are generation-shape failures that occur before any probe
could run; probes and counterexamples can only act on structurally
valid candidates. The one route that passed structurally in any
track (mn-post in B) never reached a working probe in the original
runs (see contamination note).

**Contamination incident (fully disclosed):** post-run analysis
found that the four-track runner never reset route files between
tracks — C's and D's failed mn-post loops were final-scored against
Track-B's still-installed bytes (ledger proof: D's mn-post loop =
parse-reject + stop, yet final = structural-OK). The original C/D
summaries (archived as `*-run1-contaminated/`) therefore over-credit
one piece each (7/15 → corrected 6/15). The runner was fixed
(per-domain route-file reset) and C and D were re-run from scratch:
both reproduced their loops deterministically (identical attempt
counts and token totals — C 7,078 tokens in both runs) and confirmed
6/15 each. The re-run D is also the first D with functional in-loop
probes (the original route-probe template never parsed — §9/evaluator
notes).

**Evaluator integrity during Phase 10:** the route-probe template
had, since creation, an unbalanced brace plus an unwired
`NextResponse` mock plus a `FakeReq` without `.url` — every route
probe in every run returned no-verdict (harness class) and final
scoring uniformly fell back to structural-only credit for routes.
The comparison's symmetry is preserved (all four tracks identically
affected); the fixes are committed and the adversarial suite passes
30/30 with them.

## 14. Phase 11 — Full-stack independence challenge [DONE]

Frozen spec `experiments/z037-generalization/challenge/SPEC.json`:
the Greenhouse plant-care app — 2 related prisma models (required
FK), `needsWater` boundary invariant, POST+GET routes with 4+2
behavioral probe cases, and a client page (fetch on mount,
needs-water badge, watering form, error/loading states).

**Run 1 (spec frozen at sha `0f08f72b…`, engine-only): 0/6 pieces.**
Root cause: the spec omitted `demo_domain` on entities and the UI
piece — a violation of the engine's demo-completeness contract. The
prompt said "Adapt the example's PATTERNS" with no example present;
the model echoed the L-CHECKLIST comment into comment-loops instead
of writing fields. Finding: the L-CHECKLIST amplifies demo-absence —
worse than unassisted Track-A on equivalent pieces.

**Run 2 (demo-complete amendment, frozen at sha `32ac3b42…`, only
demos added; gates/oracles/cases byte-identical; both runs archived):
engine-only 2/6.** Both prisma models resolved first-try at 300
tokens each — the same relation pair Session 036 went 0/16 on. The
invariant, both routes and the page failed (the same families that
failed in the four-track).

**The delivered app = run-2 engine pieces + disclosed teacher pass**
(full per-piece ledger in `challenge/attribution.json`, in-file
labels at every teacher touch):

| Piece | Provenance | Behavioral verification |
|---|---|---|
| gh-plant | model (1 att, 300 tok) | schema validates; probes pass against it |
| gh-watering | model (1 att, 300 tok) | relation integrity via db push + probes |
| gh-needswater | model expression (`return moisture < 30` from attempt-0 archive) + teacher assembly | 5-case boundary table + 300-case fuzz vs reference oracle PASS |
| gh-get-plants | teacher per spec clauses | route probe PASS (list-all, filter) on fresh DB |
| gh-post-watering | teacher per spec clauses | route probe PASS (400/400/404/201) on fresh DB |
| gh-page | model-influenced skeleton + teacher code | live browser verification below |

Attribution: 2 model-generated, 1 model-expression/teacher-assembly,
1 model-influenced/teacher-code, 2 teacher-written; harness scaffold
(schema head, route imports, seed data) labeled in-file.

**Live browser verification (agent-browser, real screenshots in
`challenge/screenshots/`):** the page renders the plant list with
needs-water badges (Fern, moisture 22 → badge via the model-authored
invariant); submitting amount 0 shows "Amount must be 1-500"; a
valid submit persists a watering (database-verified); zero console
errors. Two screenshots archived (initial + after-watering).

Disclosures: the page-decompose attempt in both runs had the
leftover Session-036 teacher page as its base (workspace reset gap;
the gate correctly rejected it — wrong uiStrings/accesses — loop
outcome unaffected); docgate (validated default-ON) was enabled for
the challenge while the four-track configs were frozen without it;
B's mn-post bytes from Phase 10 were overwritten by the C re-run
before post-hoc behavioral verification could be performed.

## 15. Resource accounting

| Phase | Tokens | Wall time | Notes |
|---|---|---|---|
| Four-track (A+B+C+D loops) | 55,788 | ~2.9 h total | A 21,844 / B 20,170 / C 7,078 / D 6,696; per-piece budgets enforced (6 gen / 2,000 tok) |
| Curriculum A (both arms) | 10,238 | ~50 min | 6,000 base / 4,238 engine |
| Curriculum B (both arms) | 5,449 | ~35 min | 3,642 base / 1,807 engine |
| Principle validation | ~9k | ~40 min | ledgered in principles/ |
| Docgate A/B | 10,029 | ~25 min | 5,144 without / 4,885 with |
| Challenge (run 1 + run 2) | 12,524 | ~33 min | 6,868 + 5,656 |
| C/D contamination re-run | 13,774 | ~30 min | deterministic reproduction of loops |

Model usage totals (from the track summaries' model_usage records):
A 59 generations / 21,844 new tokens / 2,528 s; B ~57 / 20,170; C 42 /
7,078; D 42 / 6,696. All inference on 2 CPU threads; the dev server
was stopped during every generation phase. The second sandbox reset
cost one discarded partial Track-A run (3 pieces, no summary,
deterministic re-run) and the environment rebuild (torch CPU wheel +
model re-download, sha re-verified against the pin).

## 16. The twelve questions

1. **Did the improved system beat the fixed baseline on unseen tasks
   at equal compute?** No. D 6/15 vs B 9/15 (−33%) on the frozen
   suite at identical per-piece budgets; D spent ⅓ of B's tokens.
2. **By how much — was ≥20% met?** Not met; the sign is negative.
   The engine's wins are family-specific: 6/6 relation schemas (B:
   5/6) with all-domain schema validity, at ⅓ the cost.
3. **Which mechanisms drove the gains?** Decomposition+laws+policy
   (C vs B isolates them): schemas 6/6 vs 5/6 and −65% tokens, but
   −3 invariants (token-cap truncation exhibit, §13). Probes+
   counterexamples (D vs C): zero delta — the failures occur before
   probes can engage. Principles: zero (none promoted). Prompt
   evolution: zero (laws stayed ahead). Curricula: demo/law shaping
   (transfer 1/2 tasks). Docgate: +2/8 on fresh tasks — the only
   validated add-on, and it flipped a GET-search piece (a universal
   four-track gap).
4. **Why did the 036 bandit lose?** Degenerate arms (53/87 attempts
   on broken prompts), Beta(1,1) uniform priors over 7 arms × 8
   attempts, structural-only rewards, token-blind micro strategies
   (§4).
5. **Were any reasoning principles promoted?** No — the pipeline
   refused all four model-reflected candidates and the teacher-seeded
   one; PR-MOD-002 was rejected as actively harmful. Honest negative:
   at 0.5B, deterministic laws already encode what principles would
   add.
6. **Did curricula transfer?** Same-family transfer 1/2 (cascade
   deletion yes, lifecycle chain no); the cross-family generalization
   lives in the laws, not the curricula.
7. **Did prompt evolution beat the deterministic laws?** No.
8. **Was the documentation workflow proven before enabling?** Yes —
   6/8 vs 4/8 at fewer tokens on fresh tasks, pre-registered rule,
   default flipped ON only after that evidence (§11).
9. **How were the three failure sources separated?** Reproducible
   archive taxonomy (§4); evaluator bugs found, fixed, disclosed with
   re-scoring impact (036 false-reject; same-line prisma fields;
   invariant object-inputs; route-probe template; cross-track
   contamination); adversarial suite 30/30 throughout.
10. **Four-track numbers with n=15 honesty?** A 4 / B 9 / C 6 / D 6.
    A two-piece swing is within noise; the invariants-vs-schemas
    trade is family-consistent, not piece-noise, but a second seed
    per piece would be required to separate seed-luck from mechanism
    — not run (CPU budget), recorded as the top follow-up.
11. **Challenge attribution?** 2 model-generated, 1 model-expression
    +teacher-assembly, 1 model-influenced+teacher, 2 teacher-written;
    engine-only 2/6 on the demo-complete spec (0/6 on the demo-less
    spec — the demo ablation); delivered app browser-verified with
    real screenshots (§14).
12. **What would make the ≥20% target credible?** (a) fix the
    invariant token cap (the truncation exhibit predicts +2–3 pieces
    for the engine — untested against the frozen suite on purpose);
    (b) larger suites (n≥30) and second seeds; (c) docgate integrated
    from the start (it flips the universal GET-search gap); (d) a
    model that can follow free-form procedural addenda, since every
    meta-layer (principles, evolved prompts) was a null result at
    0.5B while the structural layers carried everything.

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
