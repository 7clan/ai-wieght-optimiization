# SESSION 035 — UNSEEN FULL-STACK TRANSFER (final report)

**Branch:** `exp/zai-unseen-fullstack` (forked from the verified Session-034
milestone `exp/zai-visual-intelligence` @ `a997586`)
**Question:** can the frozen Qwen2.5-Coder-0.5B system (no weight changes,
fp32 CPU, seeded generation) transfer the Session-034 staged-generation
methodology to an unfamiliar, genuinely full-stack target — StockPilot,
an inventory-management app on Next.js 16 + Prisma + SQLite with a real
REST API and persistent storage?
**Answer (short):** the methodology transfers *partially and along a sharp,
now-mapped boundary*.  The backend layer (schema, types, CRUD route
bodies) is largely model-producible with staged contracts, micro-FIM
repair and honest gating; every UI component beyond a single frozen
string, and several two-token-level semantics (null-coalescing of
optional fields, integer-type validation, `a.`-qualified filters),
never appeared in ~280 archived samples and required disclosed teacher
integration.  The delivered application passes **all 38 frozen
functional checks + the visual bar (10/10 x 3 viewports)**, with
provenance recorded per file.

---

## 1. Deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Working application (live preview workspace `/home/z/my-project`, port 3000) + preserved surface on-branch | `apps/stockpilot/` |
| 2 | Live preview | Z.ai preview panel (route `/`) |
| 3 | Real browser screenshots, 1440x900 / 390x844 / 320x700 + empty state | `experiments/zai-fullstack/shots/` |
| 4 | Provenance/ownership breakdown per file | `experiments/zai-fullstack/PROVENANCE.json` + §4 below |
| 5 | Raw test evidence (frozen suites, per-check) | `experiments/zai-fullstack/reports/`, `apitest-result-*.json`, `uitest-result.json`, `vis_final.json` |
| 6 | Unassisted vs assisted comparison | §5 |
| 7 | This report | `docs/ZAI_UNSEEN_FULLSTACK.md` |
| 8 | Session-036 recommendations | §9 |

## 2. Protocol (frozen before generation)

- Spec + acceptance tests committed **before** the first generation
  (`experiments/zai-fullstack/SPEC.md`, `apitest.mjs` 16 checks,
  `uitest.mjs` 20 checks, Session-034 visual evaluator re-pointed at `/`).
- Model: local `Qwen/Qwen2.5-Coder-0.5B`, 494,032,768 params verified on
  load, sha256-pinned checkpoint, fp32 CPU 2 threads, seeded
  (greedy first, then temp 0.72 / top-p 0.93).  **No weight changes of
  any kind.**
- Track A (unassisted): the full spec as ONE monolithic prompt,
  7 candidates, mechanical install only.
- Track D (staged): small contracts → static gates (tsc/eslint/prisma/
  exports) → frozen dynamic suites → Qwen-authored repair loop
  (3 rounds x 4 samples per defect, Session-034 convention).
- Provenance labels: QWEN-ORIGINAL / QWEN-REPAIRED / TEACHER-INTEGRATION
  / TRUSTED-SCAFFOLD.  Scaffolding and teacher help are **never**
  counted as model capability.

## 3. Track A — unassisted baseline (the honest zero)

7/7 monolithic candidates generated (8,400 tokens, 1,251 s wall,
1,882 s CPU, 3,258 MB peak RSS).  **0/7 viable:** no candidate contained
a valid `InventoryItem` Prisma model; every install failed tsc
(truncated JSX / syntax); page and API 500; **0/36 frozen checks
reachable.**  Raw completions archived
(`experiments/zai-fullstack/generations/trackA_*`, reports `trackA*.log`).

## 4. Track D — staged generation: the full arc and final provenance

### 4.1 What the model produced (final file provenance)

| File | Label | How |
|---|---|---|
| `prisma/schema.prisma` (model block) | **QWEN-REPAIRED** | 3x4 completion rounds failed on `sku String?` nullability; the **first FIM micro-patch sample** fixed it (Session-032 method transfers to Prisma) |
| `src/lib/inventory/types.ts` | **QWEN-ORIGINAL** | accepted on round-0 sample 1 (whole-file contract: concept + pet-shelter demo + spec + anchor) |
| `src/app/api/items/route.ts` | **QWEN-REPAIRED** | near-miss whole-file sample `r0_k3` (QWEN-ORIGINAL bytes) + 4 landed micro-FIM patches + disclosed teacher fixes (see 4.3) |
| `src/app/api/items/[id]/route.ts` | **QWEN-REPAIRED** | GET/DELETE bodies = unmodified archived Qwen samples (mechanical prose cut); PUT body = cleanest body-contract sample + teacher fixes |
| `src/components/stockpilot/states.tsx` | **MIXED** | EmptyState + ErrorState = unmodified Qwen samples (round-0); NoMatchesState = teacher (12/12 failures) + 2 disclosed teacher edits (placeholder text swaps) |
| `toolbar / stats-bar / item-table / item-form / use-inventory / page` | **TEACHER-INTEGRATION** | every contract failed its full 3x4 budget (all samples archived); item-table's round-2 "acceptance" was a **false accept** (spec-echo) caught by tsc |

### 4.2 The escalation ladder that produced the backend

1. **Whole-file contracts** (Session-034 format): succeeded for
   `types.ts`; produced one near-miss for the list route; demo-echo
   and documentation-only completions dominated elsewhere
   (client contract dropped after an honest 2x12 echo failure).
2. **Body-granularity contracts** (handler bodies with anchors):
   reliably produced right-ordered, complete CRUD bodies — but each
   sample missed a *different* one of {`Number.isInteger`,
   `sku: sku \|\| null`, validation-before-write order}; no sample
   ever had all three (PUT: 12 samples; POST: 12; list-GET: 12+12).
3. **Micro-FIM patches** (Session-032 format, <=15-word literal
   instructions adjacent to a tiny gap): landed category-read,
   category-validate, sku-optional-check, create-data and ONE
   integer-condition patch; failed for param-reading, where-object
   construction, status-filter logic, type-level casts and the
   `sku: sku || null` literal (3+3+3 failures).
4. **Teacher integration** (disclosed, byte-counted): the residual
   ~600 bytes of semantic fixes + the six UI files above.

### 4.3 Disclosed teacher integration (complete list)

Routes (after ~100 archived samples): GET filter receiver fix
(`a.minQuantity` x2, junk-const removal), PUT restoration (integer
checks, sku-optional, sku-null), POST sku-null, where-type annotation,
order-type cast.  UI: NoMatchesState, StatsBar, Toolbar, ItemTable,
ItemForm, useInventory, page assembly, plus two placeholder-text swaps
in the model's accepted state components.  Scaffold config: one
`globals.css` rule (button cursor, Tailwind v4 preflight change) and
the test helpers.  Every edit is recorded with before/after strings in
`PROVENANCE.json` (`route-teacher`, `ui-teacher` stages).

## 5. Unassisted vs assisted (same frozen checkpoint)

| | Track A (unassisted) | Track D (staged + feedback + disclosed teacher help) |
|---|---|---|
| Viable candidates | 0/7 | application delivered |
| Frozen checks reachable | 0/36 | **38/38** (API 16 + UI 20 + persistence 2) |
| Visual bar | unreachable | **10/10 x 3 viewports** |
| Model share of application bytes | 0% (nothing installable) | backend layer largely model-authored; UI largely teacher (see §4) |
| Generations / tokens | 7 / 8,400 | 278 / 155,244 (all archived) |

The comparison is **not** "model vs teacher" — Track D's outcome is the
*frozen system* (model + harness + disclosed integration policy)
achieving what the bare model cannot.  The model's independent share
is reported per file in §4.1, never inflated.

## 6. Frozen-suite results (final, raw evidence)

- `apitest.mjs`: **16/16** (pre-phase) + **2/2** (post-restart
  persistence across a full dev-server restart; SQLite is the source
  of truth) — `apitest-result-pre.json`, `reports/trackD16.log`.
- `uitest.mjs`: **20/20, zero page errors** — `uitest-result.json`
  (both empty states, error/retry via network interception, edit and
  delete flows, live search, filters, sort, mobile 390/320 layouts,
  loading indicator, refresh persistence).
- Visual evaluator: **10/10 x 3 viewports** — `reports/vis_final.json`.
- Screenshots: `shots/stockpilot-{desktop,mobile,narrow,empty}*` (7 PNGs).

## 7. Defect ledger (all found, fixed and disclosed this session)

**Harness bugs (generation/verification machinery):**
1. brace-balance ran on completions without their anchor (3 valid schema
   samples wrongly rejected);
2. installer dropped the anchor line (every installed file began
   mid-construct);
3. / 3b. `_balanced_end` counted signature parens as construct end;
   EOL heuristic fired inside multi-line signatures (a twice-rejected
   sample trimmed to a perfect file);
4. prompt-echo regions poisoned installs (two-phase mechanical strip
   added);
5. body sanity check appended a brace to self-balanced bodies (false
   "brace imbalance" on valid samples);
6. order check inverted (rejected the correct validation-before-write
   order);
7. substring expects satisfiable by *instruction echoes* (a "landed"
   integer patch was prose);
8. substring expects satisfiable by *spec echoes* (item-table false
   accept; caught by tsc);
9. page exports gate required the literal name `default` (impossible
   for any default-exported component);
10. usage accounting double-counted in runner_d's finally block
    (ledger recomputed from per-sample records).

**Frozen-test defects (internal inconsistencies, repaired with
disclosure, no assertion weakened):**
11. apitest checks 7/9 expected counts their own seed corpus cannot
    produce (2 vs 3 USB items, 3 vs 4 low-stock); fixture corrected to
    the documented intent;
12. uitest check 13's `\b8\b` regression guard matched dates like
    11/8/2025 (fails on any day containing a standalone 8); dates
    stripped before the guard;
13. uitest's own simulated outage was counted as a page error;
14. unawaited `.count()` promises compared as NaN (loading-indicator
    check could never pass); strict-mode/`.first()` queries broke on
    the spec-mandated duplicate "Add Item" button and on responsive
    dual-rendering (hidden table cell shadowing mobile cards); a
    `waitForFunction` timing repair used `textContent` where cell
    separation only exists in `innerText`;
15. visual evaluator: v3-era rgba parser could not read Tailwind v4's
    oklch/lab computed colors (canvas-pixel conversion added) and did
    not recurse into `@layer`/`@media` for hover rules; Tailwind v4's
    removed button-cursor preflight restored as scaffold config.
    (One evaluator regex had also been stored with template-literal
    escaping damage.)

## 8. Capability boundary findings (the transfer result)

1. **Demo completeness beats component size.**  The 1,000-token table
   contract landed its *first greedy sample* when its demo showed the
   full desktop-table + mobile-card structure, while 420-token
   two-string components failed 12/12 when the demo was structural
   only.  Demos must show the exact *shape* (labels neutral), specs
   must carry the exact strings.
2. **Spec prose leaks verbatim into code.**  "quantity <= minQuantity"
   in prose became bare `minQuantity` in generated filters; the
   pet-shelter demo produced one chimera body mixing demo fields with
   target fields.  Contracts must be written as code-shaped actions.
3. **The one-literal gap.**  Across every mode, samples miss single
   literals (`sku: sku || null` 15/15 POST-lottery misses;
   `Number.isInteger` in FIM 6/6; debounce `300` 12/12 hook misses).
   Micro-FIM fixes some (schema nullability, category reads), not
   others — with no observable predictor beyond "the fix must imitate
   an in-context line".
4. **Type-level precision never appeared** (Prisma orderBy typing,
  `as 'asc' | 'desc'` casts) — 6/6 FIM failures on the two type fixes.
5. **False accepts are the dominant integrity risk**: anchor-only
   files passing tsc, instruction/spec echoes satisfying substring
   expects, promises comparing as NaN.  Every gate that reasons about
   *content* must parse structure, not substrings.

## 9. Session 036 recommendations

1. **Close the one-literal gap mechanically**: add an
   expected-AST/expected-token gate per contract (structure, not
   substrings), and a "literal patch" mode where the teacher names the
   exact token diff and the model executes it — measuring whether the
   model can *apply* a named literal even when it cannot *choose* it.
2. **Demo-completeness law**: auto-derive demos from the target shape
   (neutral labels) and measure "demo coverage" as a predictor of
   first-sample acceptance before spending sample budgets.
3. **Spec-prose compiler**: rewrite contract prose through a
   code-action template ("set X to Y", "call Z") to stop verbatim
   leakage; re-run the GET-filter ladder as the A/B test.
4. **UI transfer with per-string budgets**: the two-string boundary
   suggests splitting every UI contract at frozen strings (one per
   contract) and assembling mechanically; test whether 3-string
   components then land.
5. **Re-verify the false-accept defenses** on a fresh task: AST gates,
   anti-echo parsing, awaited predicates — then attempt StockPilot
   again with zero teacher bytes as the Session-036 success bar.

## 10. Reproducibility

- Every generation (prompt + completion + seed + token count + reject
  reason) is archived under `experiments/zai-fullstack/generations/`
  (278 samples; FIM, body, whole-file, UI and Track-A kinds).
- Run logs: `experiments/zai-fullstack/reports/trackA*.log`,
  `trackD*.log` (D1-D19 cover every round of this arc).
- Branch ledger: `BRANCH_ACTIONS.md`; provenance:
  `experiments/zai-fullstack/PROVENANCE.json`.
- Total model usage (recomputed from per-sample records): 278
  generations, 155,244 new tokens, 21,678.5 model-seconds (~6.0 h on
  2 CPU threads).  Peak model RSS ~3.0 GB (dev server stopped during
  generation, per the RAM discipline).
