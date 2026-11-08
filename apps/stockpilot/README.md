# StockPilot — Session 035 Track D application surface

The live application runs in the Z.ai preview workspace (`/home/z/my-project`,
a Next.js 16 + Tailwind v4 + shadcn/ui + Prisma/SQLite sandbox).  This
directory preserves the exact application-surface files as delivered,
for provenance and reproduction:

- `src/` — every application byte (page, API routes, stockpilot
  components, inventory lib).  Provenance per file in
  `experiments/zai-fullstack/PROVENANCE.json`:
  - `src/lib/inventory/types.ts` — QWEN-ORIGINAL (round-0 sample 1)
  - `src/app/api/items/route.ts` — QWEN-REPAIRED (near-miss base +
    micro-FIM patches + disclosed teacher fixes)
  - `src/app/api/items/[id]/route.ts` — QWEN-REPAIRED (archived body
    samples assembled + disclosed teacher fixes)
  - `src/components/stockpilot/states.tsx` — MIXED (EmptyState +
    ErrorState = unmodified Qwen samples; NoMatchesState = teacher)
  - `src/components/stockpilot/{toolbar,stats-bar,item-table,
    item-form}.tsx`, `src/lib/inventory/use-inventory.ts`,
    `src/app/page.tsx` — TEACHER-INTEGRATION (all model attempts
    archived in `experiments/zai-fullstack/generations/`)
- `prisma/schema.prisma` — model block QWEN-REPAIRED (3x4 completion
  failure repaired by the first FIM micro-patch)
- `scripts/wipe-inventory.ts` — TRUSTED-SCAFFOLD test helper
- `tsconfig.gate.json` — TRUSTED-SCAFFOLD scoped compile gate
- `globals.css.additions` — the one scaffold-config rule appended for
  the visual evaluator's interactivity metric (Tailwind v4 dropped
  the v3 button-cursor preflight)

Scores (frozen suites, final): API 16/16, persistence 2/2,
UI 20/20 with zero page errors, visual 10/10 x 3 viewports.
See `docs/ZAI_UNSEEN_FULLSTACK.md` for the full report.
