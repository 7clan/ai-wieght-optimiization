# GearHut — Session 040 demonstration app

A gear locker maintenance log (CRUD + validation + tests) demonstrating the
Session-040 pipeline end to end: a frozen spec, contract-first generation
with the frozen Qwen2.5-Coder-0.5B, restricted-tier gates, execution-feedback
repair, disclosed teacher corrections, and app-level verification.

- **Spec (frozen before generation):** `experiments/z040-autonomous-fullstack/app/APP_SPEC.json`
- **Per-piece evidence:** `experiments/z040-autonomous-fullstack/app/evidence/`
- **Raw generations (as-extracted):** `experiments/z040-autonomous-fullstack/app/generated/`
- **Attribution (byte-level, per file):** `experiments/z040-autonomous-fullstack/app/ATTRIBUTION.md`

## What is in this archive

```
prisma/schema.prisma                     models (TEACHER-CORRECTED; Qwen attempt archived)
src/lib/gear-invariant.ts                QWEN-REPAIRED state invariant (verbatim logic)
src/app/api/gearhut-items/route.ts       GET (corrected) + POST (QWEN verbatim)
src/app/api/gearhut-items/[id]/route.ts  PATCH advance (drives the Qwen invariant) + DELETE
src/components/gearhut/gear-item-manager.tsx  QWEN core + disclosed fixes + wiring
src/components/gearhut/gear-item-list.tsx     QWEN structure + vocabulary corrections
src/app/page.tsx                         TEACHER-INTEGRATED assembly (sticky footer, responsive)
src/app/layout.tsx                       metadata
scripts/seed-gearhut.ts                  demo data (idempotent)
scripts/gearhut-apitest.mjs              API suite — 25/25
scripts/gearhut-invariant-test.mjs       invariant suite — 7/7 frozen cases
screenshots/desktop.png                  1280×900 full page (live browser)
screenshots/mobile.png                   320×700 full page (live browser)
```

## Reproducing the surface in a sandbox Next.js project

1. Copy `prisma/schema.prisma`, `src/`, and `scripts/` into the project
   (the project's own `src/components/ui` shadcn set and `src/lib/db.ts`
   singleton are assumed, plus `DATABASE_URL` pointing at a SQLite file).
2. `bun run db:push && bun run db:generate && bun scripts/seed-gearhut.ts`
3. `node scripts/gearhut-apitest.mjs` (dev server on :3000)
4. `node --experimental-strip-types scripts/gearhut-invariant-test.mjs`

No application byte was edited after the Phase-6 verification runs; the
screenshots and suite results in ATTRIBUTION.md correspond to exactly these
files.
