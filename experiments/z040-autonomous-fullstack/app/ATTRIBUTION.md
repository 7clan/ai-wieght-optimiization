# GearHut — Session 040 Phase 5/6 attribution record

**Spec:** `APP_SPEC.json` (sha256 `b6c249710d91e454c9da13e75dc5b6f8835087a8fd682b87fbac597a84ad6521`, committed at `62510b1` BEFORE any generation).
**Model:** frozen `Qwen/Qwen2.5-Coder-0.5B` (safetensors sha256 `aff8914e…a47f80`, re-verified this session), greedy decoding, per-piece deterministic seeds (see evidence records).
**Prompt recipe:** the validated Track-B contract-first template (`archagent/s040/prompts.py`) reused verbatim with the app entry; the only deviation is the fullstack-integration anchor (receives a `lockers` prop), disclosed in the spec.
**Generation totals:** 9 generations (6 pieces + 1 forced-continuation retry + 2 repairs), 4,550 new tokens, 562 s model time. Per-piece evidence: `evidence/gearhut__<skill>.json` (prompt + sha, raw generation, usage, candidate, every gate verdict).
**Gates:** schema = restricted-tier behavioral probes (7); state-invariant = restricted-tier case table (7); TS/TSX = restricted-tier esbuild parse gate; all behavior additionally verified by the Phase-6 suites (API 25/25, invariant 7/7, browser interactions, screenshots).

## Piece outcomes (pre-integration)

| piece | attempts | verdict | attribution |
|---|---|---|---|
| schema-relationship | 3 (1 + 2 repairs) | BEHAVIOR_FAIL | TEACHER-CORRECTED |
| state-invariant | 2 (1 + 1 feedback repair) | BEHAVIOR_PASS | QWEN-REPAIRED |
| api-get-filter | 1 | parse PASS | QWEN_GENERATED (syntax) → vocabulary TEACHER-CORRECTED at integration |
| api-post-validation | 1 | parse PASS | QWEN_GENERATED (integrated verbatim; behavior verified 25/25 API suite) |
| react-interaction | 1 | parse PASS | QWEN_GENERATED (syntax) → vocabulary TEACHER-CORRECTED at integration |
| fullstack-integration | 1 | parse PASS | QWEN_GENERATED (core) + 3 disclosed bug fixes + teacher wiring |

## Integrated files (sandbox Next.js project; archived under `apps/gearhut/`)

| file | bytes | Qwen candidate bytes | attribution |
|---|---|---|---|
| `prisma/schema.prisma` | 1,255 | 0 | TEACHER-CORRECTED — the model's attempt (optional FK + SetNull instead of required + Restrict, missing `label`, degenerate follow-on models + prose) failed all probe rounds; archived in `generated/schema.prisma` |
| `src/lib/gear-invariant.ts` | 881 | 305 | QWEN-REPAIRED — logic verbatim from the repaired generation; teacher added TS types + header. 7/7 frozen case table passes on the integrated file |
| `src/app/api/gearhut-items/route.ts` | 2,719 | 1,092 | POST is the model's generation **verbatim** (0 repairs); GET is TEACHER-CORRECTED (the model copied the greenhouse demo: `db.sensor`, `orderBy reading`, `{ sensors }` envelope — the documented demo-vocabulary failure mode); corrections marked inline |
| `src/app/api/gearhut-items/[id]/route.ts` | 2,165 | 0 | TEACHER-CORRECTED (spec §teacher_extensions) — PATCH makes the Qwen invariant load-bearing (advance one stage only); DELETE |
| `src/components/gearhut/gear-item-manager.tsx` | 9,735 | 2,168 | QWEN core (state machine, fetch flow, create form, refresh-on-201, error display) + 3 disclosed bug fixes (missing `error` state declaration; `gear` initialized `null` crashed `.map`; input max 100 → 2000) + teacher wiring (server-side filter refetch, advance/delete actions) + shadcn presentation |
| `src/components/gearhut/gear-item-list.tsx` | 3,946 | 1,411 | QWEN structure (search/status/clear/empty-state) + vocabulary corrections (sensor→gear, calibrating/monitoring→stashed/inspected, reading→usageHours) + shadcn presentation |
| `src/app/page.tsx` | 2,203 | 0 | TEACHER-INTEGRATED — server component loads lockers, assembles both Qwen surfaces, responsive layout, sticky footer |
| `src/app/layout.tsx` | metadata only | 0 | TEACHER-INTEGRATED — title/description |
| `scripts/seed-gearhut.ts` | 1,364 | 0 | TRUSTED-SCAFFOLD (demo data) |
| `scripts/gearhut-apitest.mjs`, `scripts/gearhut-invariant-test.mjs` | — | 0 | TRUSTED test code (frozen test plan) |
| **Total integrated** | **24,268** | **4,977** | |

Qwen-attributed candidate bytes are ~20% of the integrated app by raw count; the honest qualifier is that the two largest Qwen files (manager, list) carry the model's *logic* inside teacher presentation chrome, while the two smallest teacher files (schema, [id] route) are pure teacher code. The POST route is the only file integrated byte-for-byte as generated.

## Phase-6 verification (all executed, none simulated)

- API suite `scripts/gearhut-apitest.mjs`: **25/25** (envelope, case-insensitive search, exact status filter, `all`, combined, empty state, 201/400×3/404/409 POST paths, persisted read-back, legal advance 200, retired-backward 409, skip-stage 409, delete 204 + gone)
- Invariant suite `scripts/gearhut-invariant-test.mjs`: **7/7** frozen cases against the integrated file
- Browser (agent-browser, live dev server): initial render + totals; server-side search filter; status filter; quick-filter client-side card; clear filters; explicit empty state (`Gear (0)` + message); create-appears-without-reload (total 6→7); duplicate create → `role=alert` error with form values preserved; advance (stashed→inspected); delete (row gone, total back to 6); 320 px viewport with **zero horizontal overflow**; sticky footer verified (footer bottom === viewport bottom, 0 px gap) and naturally pushed on long pages; **zero page errors, zero hydration warnings** in the browser console and the dev log
- Screenshots: `screenshots/desktop.png` (1280×900 full page), `screenshots/mobile.png` (320×700 full page)

## Known limitations (disclosed, not hidden)

1. The GET route's Prisma `contains` relies on SQLite `LIKE` ASCII case-insensitivity plus a JS-side `toLowerCase` backstop (the frozen convention; `mode: "insensitive"` is rejected by Prisma SQLite).
2. The duplicate check is global (not per-locker), matching the frozen POST contract.
3. The react-interaction and api-get-filter pieces were gated at syntax level pre-integration (frozen gate policy); their behavioral verification is the Phase-6 app-level suite, not a restricted-tier react oracle.
4. The `[id]` PATCH/DELETE route is teacher code per the frozen spec's `teacher_extensions` (its purpose is to make the Qwen invariant observable in the demo).
5. The model's schema attempt was not salvageable; the integrated schema is teacher-authored to the frozen contract (the attempt is archived with its probe verdicts).
