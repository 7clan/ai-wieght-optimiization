# SESSION 036 — SELF-IMPROVING QWEN, VERIFIED SELF-REPAIR & ZERO-TEACHER FULL-STACK TRANSFER (final report)

**Branch:** `exp/zai-self-improving-fullstack` (forked from the verified
Session-035 milestone `exp/zai-unseen-fullstack` @ `2782067`)
**Application:** **RoomReserve** — a meeting-room reservation manager whose
core difficulty is time-window logic (overlap prevention, boundary
conditions, availability filtering), deliberately different from TaskFlow
(task boards), MediVault (records) and StockPilot (inventory CRUD).
**Frozen model:** `Qwen/Qwen2.5-Coder-0.5B`, 494,032,768 params, fp32 CPU,
2 threads, seeded generation; checkpoint sha256 re-verified against the
Session-035 pin (`aff8914e…a47f80`) after a fresh download into a rebuilt
sandbox. **No weight changes of any kind, throughout.**

---

## Executive summary

| Question | Answer |
|---|---|
| Can the frozen 0.5B solve an unfamiliar full-stack app unassisted? | **No.** Track A: 0/7 viable candidates, 0 frozen checks reachable |
| Do corrected structural gates eliminate the documented false accepts? | **Yes.** 30/30 adversarial cases; the controller's own spurious rewrite was caught in bring-up |
| Does adaptive strategy selection beat the fixed ladder on a new task? | **No — the opposite.** Track C 4/12 vs Track B 7/12 at equal token budgets (Level-2 negative result) |
| Did any zero-teacher track produce the overlap logic? | **No.** The time-window contract failed 8/8 in both staged tracks |
| Is a complete application deliverable with disclosed integration? | **Yes.** API 24/24, persistence 2/2, UI 20/20 (0 page errors), held-out 12/12, visual 10/10 × 3 viewports |
| Did the model's intrinsic capabilities change? | **No — and this session never claims so.** Every improvement is in the surrounding system; the weights are frozen |

The three success levels: **Level 1 (engineering) achieved** — the new
validation and repair infrastructure runs reliably and rejects every
known false-acceptance shape. **Level 2 (system-level learning) NOT
achieved** — measured honestly, adaptive selection underperformed the
fixed ladder at practical budgets. **Level 3 (full-stack independence)
NOT achieved** — five load-bearing files required teacher integration.

---

## 1. Checkpoint and hardware

- Frozen checkpoint: `Qwen/Qwen2.5-Coder-0.5B` (safetensors 988,097,824
  bytes, sha256 `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`,
  identical to the Session-035 pin). Downloaded fresh into this third
  sandbox; `FrozenModel` verifies 494,032,768 params / 24 layers /
  hidden 896 on load.
- Hardware: 2 CPU threads, 3.9 GiB RAM, fp32, torch 2.15 CPU,
  transformers 5.22.2. One model instance at a time; the dev server is
  stopped during generation phases (Session-035 RAM discipline,
  enforced by `archagent/fullstack/devserver.py`).
- Generation: greedy first candidate, then temperature 0.72 / top-p
  0.93, seeded; every attempt archived with prompt + seed + token
  count + candidate sha + gate verdict.

## 2. Phase 0 — recovery and reproduction

Rebuilt from nothing in a fresh sandbox: repo clone (milestone commit
verified byte-identical), model re-download (hash-pinned), inference
stack rebuild, StockPilot surface restored **from the on-branch
archive** `apps/stockpilot/` with zero application edits.

Reproduction of the Session-035 milestone, clean checkout:
**API 16/16, persistence 2/2 (full dev-server restart), UI 20/20 with
zero page errors, visual 10/10 × 3 viewports**; 7 fresh screenshots;
raw transcripts in `experiments/zai-fullstack/reports/s036-repro/`.
One environment-sequencing artifact recorded (stale Prisma client
before first restart — not an application defect). **The archived
milestone builds and tests independently of its original preview
environment.**

## 3. Phase 1 — the structural validation system (`archagent/verify`)

Replaces Session-035's text/substring gates (the documented source of
false accepts) with TypeScript-compiler-API analysis:

- required expressions must exist as **AST nodes** — comments, string
  literals and unreachable regions can never satisfy a gate;
- route gates require **function-like exported handlers** (import-only
  "anchor" files, unexported consts, string consts, re-exports all
  rejected);
- **reachability analysis** (statements after unconditional
  return/throw; `if (false)` / `while (false)` bodies) — validation
  logic in dead code never counts;
- **`exprs` gate**: normalized AST binary-expression expectations
  (e.g. `a.quantity<=a.minQuantity`) — added after the controller's
  own self-test exposed a spurious rewrite that passed weaker gates;
- **used-position UI strings** (JSX text/attribute/call-argument or
  referenced constant — never comments or dead constants);
- **echo-fraction** detection on comment+string n-grams;
- comment-safe, truncation-safe **Prisma schema parser**;
- **cross-file interface gates** (every `db.<model>` must exist in the
  parsed schema; declared imports must be present — demo contamination
  caught mechanically);
- **error classification** (`app` / `harness` / `unknown`): harness
  defects never count against the application (NaN comparisons are
  always harness, per Session-035 #14).

**The evaluator was tested before it judged Qwen**: 30/30 adversarial
cases (`archagent/verify/adversarial.test.mjs`), including every
documented Session-035 false-accept shape (A: import-only routes;
B: comment/constant/bulk echoes; C: unreachable validation; D:
truncation; E: schema nullability/comment-fields; F: type members;
G: **six real archived StockPilot files still pass** — no false
rejects; H: this session's own spurious filter rewrite). Three
evaluator defects were found and fixed during bring-up with full
disclosure (scanner skipTrivia blinding the echo gate; a regex that
escaped its own escapes; import collection never populated).

## 4. Phases 2–3 — the self-repair controller (`archagent/repair`)

- **Error taxonomy** (9 general categories) grounded in fresh mining of
  the 278 archived Session-035 generations (`experiments/z036/prior-mining.json`).
- **Strategy space** (9 general strategies): regen_whole, exact_shape,
  body_completion, fim_micro, ast_replace, compiler_guided, doc_lookup,
  contract_split, minimal_diff. No task-solution database exists
  anywhere in the controller — arms describe HOW to attempt repairs,
  never WHAT the fix is.
- **Policy**: Thompson sampling over Beta posteriors per
  (category × strategy), priors = discounted Session-035 mining.
- **Surgical minimal-patch workflow**: original preserved, exact diff
  recorded (prompt + candidate + sha archived per attempt), parse →
  structural gates → optional isolated probe → keep-or-revert on
  evidence; regressions always rejected.
- **Provenance levels kept strictly separate**: L1 (semantic diagnosis,
  model chooses the fix), L2 (diagnosis names the code / teacher names
  the diff — model applies), L3 (harness-inserted), L4 (teacher-
  written). L1 successes are never blended with L2/L3/L4.

**Controller self-test with real inference** (3 surgically injected
defects in the archived StockPilot route): D2 (`Number.isInteger`
validation removed) **repaired by `minimal_diff` from a semantic
diagnosis alone — L1 provenance**, 4 attempts / 1,094 tokens; D1
(the documented `sku: sku || null` one-literal gap) confirmed
unrepairable (6 attempts); D3 initially produced a spurious "fix"
(dropping the comparison entirely) that the *weaker* contract
accepted — the hardened `exprs` gate now rejects it (adversarial
case H1). Five controller defects found and fixed during bring-up
(anchor/spec KeyErrors, archive-name collision, tsc OOM discipline,
diagnosis-based provenance), all disclosed in the commit history.

## 5. Phase 4 — documentation-assisted reasoning

Bounded docs bundle (`experiments/z036-roomreserve/docs-bundle/`):
official Next.js route-handler reference and Prisma client CRUD
reference, each with source URL, retrieval date and page/file sha256
(`MANIFEST.json`). Retrieved documentation is embedded as untrusted
reference material in `doc_lookup` prompts only. Measured outcome:
**doc_lookup 0/8 in Track C** — documentation access did not
materially improve any zero-teacher result this session (recorded as
a negative finding, not hidden).

## 6. Phase 5 — the frozen RoomReserve challenge

`experiments/z036-roomreserve/SPEC.md` + `apitest.mjs` (24 public
checks — the SPEC §5 text says "18", an inaccurately-transcribed count
for the as-implemented suite; disclosed here) + `uitest.mjs` (20) +
`heldout.mjs` (12, never shown to any track) — all committed at
`c310978` **before the first RoomReserve generation**. Contracts
(`archagent/fullstack/rr_contracts.py`) encode the Session-035 laws:
demo-complete shapes with neutral labels, code-action specs, AST
expectations, and a different-domain overlap demo (hotel spa
treatments) so the pattern must be adapted, not copied.

**Frozen budgets:** Track A 7 candidates × 1,500 tokens; Tracks B/C
8 generations per contract, identical gates, zero teacher bytes.

## 7. Phase 6 — the three-way comparison (same frozen checkpoint)

| | Track A (unassisted) | Track B (fixed ladder) | Track C (adaptive bandit) |
|---|---|---|---|
| Viable outcome | **0/7 candidates** | 7/12 contracts | 4/12 contracts |
| Generations / tokens | 7 / 10,500 | 60 / 15,130 | 87 / 15,467 |
| Model seconds | 1,576 | (within 2,109 s wall) | (within 2,120 s wall) |
| Assembly: tsc / API / UI / held-out | — | 13 errors (schema cascade) / 0 / 0 / 0 | 12 errors / 0 / 0 / 0 |

Track A details: two candidates extracted 6 files but placed handlers
in the wrong files (POST in the rooms route); three produced one file;
two produced nothing extractable. **0/24 frozen API checks reachable
for any candidate** — the honest zero reproduces on a second unseen
task.

Track B resolved: rooms/[id], reservations/[id], states, room-panel,
**reservation-table and reservation-form and hook on the FIRST exact-
shape sample** (the demo-completeness law transferring to a new
domain). Failed: schema (relation fields dropped 8/8), types,
rooms-route, reservations-route, page.

Track C resolved: rooms/[id], reservations/[id], reservation-form,
hook. **Per-strategy success rates (C):** exact_shape 2/12, regen_whole
1/14, body_completion 1/3, minimal_diff 0/13, contract_split 0/10,
compiler_guided 0/11, ast_replace 0/11, doc_lookup 0/8, fim_micro 0/5.

### The ablation result (Level 2 — honest negative)

**Adaptive selection underperformed the fixed ladder: 4/12 vs 7/12 at
equal token budgets.** Why, from the ledger:

1. **Exploration does not amortize at 8-attempt budgets.** Track B
   spends 6 of 8 attempts per contract on `exact_shape` (the winning
   family); the bandit spreads attempts across 5–7 strategies.
2. **The priors pointed away from the winner.** Session-035's archive
   has no `exact_shape` successes for UI-shaped contracts (its whole-
   file wins map elsewhere), so the UI categories started with
   uniformly-negative evidence and uniform posteriors elsewhere — the
   bandit had to *learn within the run* what B knew *by design*.
3. **Within-category structure WAS learned:** the bandit's final
   `missing_call|body_completion` posterior is 0.56 (highest non-
   trivial arm), and `wrong_contract|fim_micro` retains the inherited
   0.41 — the policy updates are real, the budget was too small to
   exploit them.
4. **The one-literal/UI-string boundary persists**: every
   `missing_literal` arm ≤ 0.29 across all nine strategies.

**Transfer measurement:** strategies learned from Session-035 errors
did **not** measurably help resolve different, unfamiliar errors at
these budgets. What *did* transfer is contract *design* (demos,
code-action specs, AST gates) — Track B's 7/12 versus Session-035's
UI failures is the system-level gain, and it is a **prompt/gate**
gain, not a policy gain.

## 8. Phase 7 — assisted completion (strictly separate)

Zero-teacher scores were frozen and pushed before any integration.
The delivered application = Track-B model bytes for 7 files + 5
teacher-written files + itemized repairs, per-file in
`experiments/z036-roomreserve/PROVENANCE.json`:

| File | Label | Note |
|---|---|---|
| `prisma/schema.prisma` | TEACHER-INTEGRATION | relations never appeared (8/8 both tracks) |
| `src/lib/roomreserve/types.ts` | TEACHER-INTEGRATION | 8/8 both tracks |
| `src/app/api/rooms/route.ts` | TEACHER-INTEGRATION | 8/8 both tracks |
| `src/app/api/reservations/route.ts` | TEACHER-INTEGRATION | **the overlap logic** — never appeared zero-teacher |
| `src/app/page.tsx` | TEACHER-INTEGRATION | assembly |
| `rooms/[id]/route.ts` | QWEN-REPAIRED | demo relation `bookings`→`reservations`, async params, `{room}` shape |
| `reservations/[id]/route.ts` | QWEN-REPAIRED | missing `return` on 404, PUT merge (organizer/roomId) |
| `states.tsx` | QWEN-REPAIRED | "Add Plant" demo leak → 1-string fix |
| `room-panel.tsx` | QWEN-REPAIRED | typed props, conditional availability badge |
| `reservation-table.tsx` | QWEN-REPAIRED | first-sample Qwen; WCAG button hit areas |
| `reservation-form.tsx` | MIXED | Qwen field-set/labels; teacher interaction logic |
| `use-reservations.ts` | QWEN-REPAIRED | POST→GET+params, rooms fetch, stale-closure fix |

Teacher-written bytes are never counted as model capability. The most
instructive repair: the hook **passed every structural gate while
fetching the list via POST** — structure-level verification cannot
replace behavioral tests.

## 9. Phase 8 — real validation and screenshots

Final regression (all suites re-run in sequence after the last fix):

- `apitest.mjs --phase pre`: **24/24**
- dev-server restart + `--phase post-restart`: **2/2** (SQLite persisted)
- `uitest.mjs`: **20/20, zero page errors** (conflict-in-dialog, Escape,
  edit, cancel-with-confirm, availability filter, outage/retry,
  390/320 overflow 0px)
- `heldout.mjs`: **12/12** (nested/zero-length/cross-midnight windows,
  idempotent cancel, slot reuse, combined filters, malformed JSON)
- visual evaluator: **10/10 × 3 viewports** (1440×900, 390×844, 320×700)
- 8 real screenshots (Playwright, from the running app):
  `experiments/z036-roomreserve/shots/`
- Agent-browser live verification: render, dialog flow, 409 → in-dialog
  alert, API-created booking visible in UI, 390 overflow 0, sticky
  footer 844/844 on short pages and natural push-down on long pages.

**Fixture repairs (4, all disclosed in-suite, none weakening an
assertion; every track scored 0 on the affected suites anyway):**
#1 apitest check-23 arithmetic (expected 5, own seed math yields 6);
#2 post-restart expected seed count instead of the pre-phase outcome;
#3 uitest check-20 `.first()` matching the hidden desktop table cell
at 320px (same class as Session-035 #14); #4 held-out H6 used a room
whose own seed overlaps the window (moved to Cove; H10 recount).

## 10. Phase 9 — resource efficiency

| Measurement | Value |
|---|---|
| Scored model generations (A+B+C+controller self-test) | 170 |
| Tokens generated (scored) | 45,171 |
| Model-seconds (scored) | ~6,353 s (A: 1,576; B+C within 4,229 wall; self-test 549) |
| Peak model RSS | ~2.3 GB (fp32 0.5B; dev server stopped during generation) |
| Test executions this session | ~40 suite runs |
| Teacher-written bytes (assisted phase) | 5 files + itemized repairs (PROVENANCE.json) |
| Functional checks passed per 10k generated tokens (delivered app) | 12.84 |
| Model downloads | 1 (hash-verified); archived generations never regenerated | 

Full data: `experiments/z036-roomreserve/reports/resources.json`.

## 11. False-acceptance audit (the session's core discipline)

Caught and rejected **before** they could inflate any score: the
controller's spurious filter rewrite (became adversarial case H1);
the tRPC-style export masquerade (Track A k1); comment-only
expressions; unreferenced string constants; unreachable validation;
truncated bodies/JSX/schema; wrong nullability; comment-only schema
fields; the POST-listing hook (caught by dynamic tests, not gates).
Caught in my *own* tooling during bring-up (all fixed with
disclosure): 3 evaluator defects, 5 controller defects, 4 frozen-test
fixture defects, 1 assemble-script health check, the tsconfig.gate
install omission. The evaluator suite (30/30) is committed and
re-runnable.

## 12. What transferred and what did not

**Transferred (system-level, not model-level):**
1. Demo-complete contract design → 3 first-sample UI/component
   acceptances in Track B (Session 035: 12/12 failures on the same
   class of work).
2. AST-level gating → zero false accepts survived into any score.
3. The staged escalation arc → 7/12 contracts zero-teacher (Session
   035's comparable backend layer was largely model-producible too).

**Did not transfer:**
1. Time-window logic (overlap semantics) — the session's target
   difficulty — never appeared in any zero-teacher sample.
2. Schema relations — 8/8 failures in both tracks.
3. One-literal gaps — unchanged from Session 035.
4. Adaptive strategy *policy* — the bandit's learned preferences did
   not pay for their exploration cost at practical budgets.

## 13. Reproduction

```bash
# model: local Qwen2.5-Coder-0.5B, sha256-pinned (see §1)
export ARCHAGENT_MODEL_DIR=/home/z/models/Qwen2.5-Coder-0.5B
cd ai-research && /home/z/qwen-env/bin/python -m archagent.repair.mine_priors
NODE_PATH=<ws>/node_modules node archagent/verify/adversarial.test.mjs   # 30/30
# tracks (each: gen phase stops dev server; test phase restarts it)
/home/z/qwen-env/bin/python -m archagent.fullstack.rr_track_a gen|test
/home/z/qwen-env/bin/python -m archagent.fullstack.rr_reset
/home/z/qwen-env/bin/python -m archagent.fullstack.rr_track_bc B   # or C
/home/z/qwen-env/bin/python -m archagent.fullstack.rr_assemble B    # or C
# delivered app (workspace /home/z/my-project, port 3000):
node experiments/z036-roomreserve/apitest.mjs --phase pre|post-restart
node experiments/z036-roomreserve/uitest.mjs
node experiments/z036-roomreserve/heldout.mjs
node archagent/visual/evaluator.mjs --base http://127.0.0.1:3000/ \
  --waitfor h1 --viewports "1440x900,390x844,320x700"
```

All raw evidence: `experiments/z036-roomreserve/{generations,reports,
shots,trackB-surface,trackC-surface,docs-bundle}`,
`experiments/z036/` (priors, self-test, adversarial suite),
`experiments/zai-fullstack/reports/s036-repro/`. Pushed checkpoints:
`5d3dc99` (P0), `6723803` (P1), `d2e033c` (P2/3), `c310978` (freeze),
`05d2335` (A+B), `0a92435` (C), `cbf9037` (delivered).

## 14. Session 037 recommendation

1. **Make the bandit earn its keep with amortizable budgets**: the
   clearest negative result is that 8-attempt contract budgets cannot
   repay exploration. Re-run the ablation with (a) per-category
   budgets pooled across contracts (learn on the first 4 contracts,
   spend on the last 8), or (b) 24-attempt budgets on a 6-contract
   task — measuring whether the SAME policy that lost at 8 wins at 24.
2. **Attack the schema-relations gap specifically**: relations failed
   16/16 across tracks. A dedicated contract family (one relation per
   contract, FIM on the relation line) plus the `exprs` gate extended
   to Prisma structure is the highest-value single experiment.
3. **Behavioral probes inside the loop**: the POST-listing hook passed
   all structural gates. Wire one live API probe per route contract
   (dev server + model coexistence is affordable if tsc stays
   out-of-loop) so Track C's feedback signal includes behavior, not
   only structure.
4. **Try time-window logic with decomposed contracts**: the overlap
   condition `start < existing.end && existing.start < newEnd` never
   appeared whole; test whether a boundary-table contract (explicit
   touching/nested/partial cases as code-shaped actions) lets the
   model assemble it.
5. **Keep the fixed ladder as the default**: until (1) succeeds, the
   evidence says a well-designed fixed escalation plus demo-complete
   contracts is the better system — adaptive policy is a research
   direction, not yet an engineering win.

## 15. Closing statement

The weights never changed. Everything measured here — the honest
zeros, the 7/12, the 4/12, the 24/24 — is a property of a frozen
0.5B model inside varying systems. This session strengthened the
system's *integrity* (structural verification, provenance
separations, adversarial evaluator discipline) more than its *score*,
and the report records the negative results with the same rigor as
the positive ones.
