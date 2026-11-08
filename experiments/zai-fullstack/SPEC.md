# StockPilot — Frozen Specification (Session 035)

**Status: FROZEN.** This document and the acceptance tests in this
directory are committed BEFORE the first model generation. They define
the contract for both experimental tracks. No requirement may be added,
removed or reinterpreted after generation begins; defects found later
are repaired AGAINST this spec, never by editing it.

Target: a responsive, genuinely full-stack inventory management
application running in the Z.ai preview workspace (Next.js 16 App
Router + Prisma + SQLite). This is an UNSEEN domain for the frozen
model: no prior session generated TypeScript, React/TSX, Prisma
schemas, or REST route handlers.

---

## 1. Data model (single persistent entity)

`InventoryItem`:

| Field | Type | Rules |
|---|---|---|
| `id` | string | PK, cuid, server-generated |
| `name` | string | required, trimmed, 1–80 chars |
| `category` | string | required, trimmed, 1–40 chars |
| `sku` | string | optional, trimmed, ≤ 40 chars, unique |
| `quantity` | int | required, 0 … 1,000,000 |
| `minQuantity` | int | required, 0 … 100,000 (low-stock threshold) |
| `updatedAt` | datetime | server-managed |

**Stock status rule (frozen):**
- `quantity === 0` → **out of stock**
- `0 < quantity <= minQuantity` → **low stock**
- else → **in stock**

## 2. API contract (all JSON, under `/api/items`)

| Method & Path | Semantics | Success | Errors |
|---|---|---|---|
| `GET /api/items` | list; query params below | 200 `{items, total}` | — |
| `POST /api/items` | create from `{name, category, sku?, quantity, minQuantity}` | 201 `{item}` | 400 `{error}` |
| `GET /api/items/:id` | fetch one | 200 `{item}` | 404 `{error}` |
| `PUT /api/items/:id` | full replace, same validation as POST | 200 `{item}` | 400 / 404 |
| `DELETE /api/items/:id` | remove | 204 (empty body) | 404 |

List query params (all optional, composable):
- `q` — case-insensitive substring match against `name` OR `sku`
- `category` — exact match; `all` or absent = no filter
- `status` — `low` | `out` | `ok` | `all` (default `all`), per the frozen status rule
- `sort` — `name` | `quantity` | `updatedAt` (default `updatedAt`)
- `order` — `asc` | `desc` (default `desc`)

Validation errors return HTTP 400 with body `{"error": "<message>"}`.
Server errors return 500 with the same shape. Unknown `id` → 404.

## 3. UI contract

Layout (single page, `/`):
1. **Header** — app name “StockPilot”, subtitle, “Add Item” button.
2. **Stats bar** — four cards: Total items, Total units, Low stock,
   Out of stock (computed from the CURRENT filtered list is acceptable;
   from the full inventory is also acceptable — the tests only check
   presence and numeric sanity).
3. **Toolbar** — search input (placeholder names it), category select,
   status select, sort select, order toggle. Controls labelled or
   labelled-by-placeholder.
4. **Item list** — desktop (≥768px): table with columns Name, SKU,
   Category, Quantity, Status, Updated, Actions (Edit + Delete buttons).
   Mobile (<768px): stacked cards with the same information.
5. **Item form** — dialog: fields Name, Category, SKU (optional),
   Quantity, Min quantity; inline field errors; Save/Cancel.
6. **Delete confirmation** — explicit confirm dialog before deleting.
7. **Toasts** — success on create/update/delete; error feedback on
   failed operations.

States (all three required and distinct):
- **Loading** — visible skeleton/spinner on first fetch and refetch.
- **Empty** — (a) no inventory at all: distinct message + call to
  action; (b) no matches for active filters: distinct message that
  mentions clearing filters/search.
- **Error** — fetch failure shows an error panel with a Retry button
  that recovers when the API recovers.

Status badges: “Out of stock” (destructive tone), “Low stock”
(warning tone), “In stock” (success/neutral tone).

**Frozen accessible names and strings** (the acceptance tests target
these exactly; the UI must expose them as visible text or accessible
names):
- Header button: **“Add Item”**; app title contains **“StockPilot”**.
- Search input: placeholder or label containing **“Search”**.
- Selects: **“Category”** (first option “All categories”), **“Status”**
  (options “All statuses”, “In stock”, “Low stock”, “Out of stock”),
  **“Sort by”** (options “Updated”, “Name”, “Quantity”), **“Order”**
  (options “Descending”, “Ascending”).
- Table column headers: Name, SKU, Category, Quantity, Status,
  Updated, Actions; row action buttons accessible-named **“Edit”**
  and **“Delete”**.
- Form dialog: field labels **“Name”, “Category”, “SKU”, “Quantity”,
  “Min quantity”**; submit button **“Save”**; cancel **“Cancel”**.
- Empty-inventory state: contains the text **“No items yet”** plus a
  call to action mentioning adding an item.
- No-match state: contains the text **“No items match”** plus a
  **“Clear”** control (accessible name containing “Clear”).
- Error state: panel containing the word **“error”** (case-insensitive)
  and a button accessible-named **“Retry”**.
- Loading state: an element with **role="status"** or visible text
  matching **/loading/i** while a fetch is in flight.
- Success feedback: a transient element with **role="status"**
  (toast) after create/update/delete.
- Delete confirmation: a dialog that mentions deleting and requires
  an explicit confirm action before the item disappears.

Persistence: data survives page refresh AND dev-server restart
(SQLite file is the source of truth; no in-memory-only storage).

## 4. Responsive & visual requirements

- Viewports that must work: 1440×900 (desktop), 390×844 (mobile),
  320×700 (narrow mobile). No horizontal overflow at any of them.
- Visual quality bar: Session 034’s calibrated evaluator
  (`archagent/evaluator.mjs` reuse), 10 metrics, must reach 10/10
  on each of the three viewports after the repair stage:
  text-visibility, no-overlap, no-h-overflow, button-visibility
  (WCAG 2.2 ≥24px), alignment, typography-consistency, contrast,
  interactivity, visual-hierarchy, responsive-adaptation.
- Touch targets ≥ 24px (44px preferred), focus styles preserved.

## 5. Frozen acceptance tests

- `apitest.mjs` — 16 ordered API assertions (§2), including
  validation, filtering, sorting, 404s and the restart-persistence
  check.
- `uitest.mjs` — 20 ordered browser steps (§3) with Playwright,
  including both empty states, the error/retry path (simulated API
  outage via request interception), edit and delete flows, and mobile
  layout checks at 390×844 and 320px.
- The unchanged Session 034 visual evaluator, re-pointed at
  `http://127.0.0.1:3000/`.

A track is FUNCTIONALLY COMPLETE only when apitest and uitest pass
end-to-end with zero page errors, and the app persists across a
dev-server restart.

## 6. Experimental protocol (frozen)

Model: local `Qwen/Qwen2.5-Coder-0.5B` (494,032,768 params verified
on load), fp32, CPU, 2 threads, seeded generations; temperature 0.72
/ top-p 0.93 when sampling. No weight changes of any kind.

- **Track A (unassisted baseline).** The model receives the
  application spec (§1–§3) as ONE prompt in the Session-034 monolithic
  style and must produce the application. Up to 7 candidates
  (first greedy, then sampled; seeds 0,1013,2026,3039,4052,5165,6278).
  No staging, no feedback, no retries beyond the candidate budget.
  Acceptance for a candidate: it compiles as TypeScript and passes the
  frozen acceptance tests after mechanical installation only
  (file placement, no content edits).
- **Track D (staged + execution feedback).** The application is
  decomposed into small contracts (schema → types → API routes →
  components → page assembly → polish). Every piece is generated from
  an exact-shape prompt (concept + different-domain demo + measurable
  spec + anchor), gated by static checks (tsc/eslint/prisma) and the
  frozen tests, with a Qwen-authored repair loop for measured defects
  (max 3 rounds × 4 samples per defect, Session-034 convention).
- **Provenance labels** per file: `QWEN-ORIGINAL`, `QWEN-REPAIRED`,
  `TEACHER-INTEGRATION` (disclosed integration help),
  `TRUSTED-SCAFFOLD` (pre-existing project infrastructure: Next.js
  scaffold, shadcn/ui primitives, Prisma client, test harness).
- **Measurements**: wall-clock, model CPU time, peak RSS, total
  generations, tokens generated, accepted/rejected counts per track.
- Generated code executes only inside the sandboxed preview workspace
  with resource limits; no network egress from generated code.

## 7. Scoring (frozen, Session-034 scale)

- Functional: apitest (16) + uitest (20) = 36 checks, pass/fail each.
- Visual: 10 metrics × 3 viewports; score = min across viewports.
- Provenance: share of application bytes by label (never counted as
  model capability for TEACHER-INTEGRATION or TRUSTED-SCAFFOLD).
