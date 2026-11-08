# RoomReserve — FROZEN SPECIFICATION (Session 036)

**Status: FROZEN before first model generation.** Any change after
generation starts must be a disclosed, versioned fixture repair (with the
competing tracks re-run against the corrected fixture).

RoomReserve is a meeting-room reservation manager. It is deliberately
different from TaskFlow (task boards), MediVault (medical records) and
StockPilot (inventory CRUD): its core difficulty is **time-window logic**
(overlap prevention, boundary conditions, availability filtering), not
item counting.

Stack (fixed by the preview workspace): Next.js 16 App Router +
TypeScript + Tailwind v4 + shadcn/ui + Prisma + SQLite (`/home/z/my-project`).

---

## 1. Data model (Prisma, SQLite)

```prisma
model Room {
  id        String        @id @default(cuid())
  name      String
  capacity  Int
  floor     Int
  createdAt DateTime      @default(now())
  reservations Reservation[]
}

model Reservation {
  id         String   @id @default(cuid())
  roomId     String
  title      String
  organizer  String
  start      String          // ISO local datetime "YYYY-MM-DDTHH:mm"
  end        String          // ISO local datetime "YYYY-MM-DDTHH:mm"
  status     String   @default("confirmed")  // "confirmed" | "cancelled"
  createdAt  DateTime @default(now())
  room       Room     @relation(fields: [roomId], references: [id])
}
```

Nullable fields: NONE in Room; NONE in Reservation (all required).
`start`/`end` are plain ISO local strings — no timezone math.

## 2. API contract

All responses are `NextResponse.json`. Errors: `{ "error": string }`
with the stated status code.

### 2.1 GET /api/rooms
- 200 `{ "rooms": Room[], "total": number }`
- Query `?q=` case-insensitive match on room name (substring).
- Query `?minCapacity=<int>` keeps rooms with `capacity >= minCapacity`.
- Ordered by `name` ascending.

### 2.2 GET /api/rooms/:id
- 200 `{ "room": Room }` (with `reservations` relation included, newest
  first by `start` descending)
- 404 `{ "error": "Room not found" }`

### 2.3 GET /api/reservations
- 200 `{ "reservations": ReservationView[], "total": number }`
- `ReservationView` = reservation fields + `roomName: string` (joined).
- Default: `status = "confirmed"` only, ordered by `start` ascending.
- Query `?date=YYYY-MM-DD` — only reservations overlapping that day
  (`start < date+1day 00:00` and `end > date 00:00`).
- Query `?roomId=<id>` — only that room.
- Query `?includeCancelled=1` — also cancelled ones.
- Query `?q=` — case-insensitive substring on title or organizer.

### 2.4 POST /api/reservations
Body: `{ roomId, title, organizer, start, end }` (JSON).
Validation (in order; first failure wins):
1. `title` non-empty after trim → else 400 `"Title is required"`
2. `organizer` non-empty after trim → else 400 `"Organizer is required"`
3. `roomId` is a string, matches an existing Room → else 404 `"Room not found"`
4. `start`/`end` match `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$` → else 400
   `"Invalid date format"`
5. `start < end` as strings (ISO local compares lexicographically) →
   else 400 `"End must be after start"`
6. No overlap with any **confirmed** reservation in the same room:
   overlap ⟺ `new.start < existing.end && existing.start < new.end`
   (back-to-back `existing.end == new.start` is NOT an overlap) →
   else **409** `{ "error": "Time conflict with an existing reservation" }`
- Success: 201 `{ "reservation": ReservationView }` with
  `status: "confirmed"`.

### 2.5 PUT /api/reservations/:id
- Body may contain any of `title, organizer, start, end, roomId`.
- 404 `"Reservation not found"` for unknown id.
- Same validation as POST, applied to the merged result. Overlap check
  must EXCLUDE the reservation being edited.
- Success: 200 `{ "reservation": ReservationView }`.

### 2.6 DELETE /api/reservations/:id — CANCELLATION
- 404 for unknown id.
- Sets `status = "cancelled"` (soft cancel; row is kept).
- Success: 200 `{ "reservation": ReservationView }` (cancelled).
- A second DELETE on an already-cancelled row: still 200 (idempotent).

### Conflict semantics (frozen)
- Same room, overlapping confirmed window → 409 on POST and PUT.
- Cancelled reservations NEVER block (excluded from overlap checks).
- Different rooms never conflict with each other.
- Boundary: `end == start` touching windows do NOT conflict.

## 3. Seed data (synthetic; wiped and re-seeded by the test harness)

Rooms (created in this order):
1. `Atlas Boardroom`, capacity 12, floor 3
2. `Breeze Huddle`, capacity 4, floor 1
3. `Cove Focus Room`, capacity 2, floor 2
4. `Dune Workshop`, capacity 8, floor 3

Reservations (all `confirmed` unless noted): seeded relative to a fixed
test date `2026-11-12` (no timezone arithmetic — literal ISO strings):
- R1 Atlas, "Quarterly Review", "Ava Chen", 2026-11-12T09:00 → 10:30
- R2 Atlas, "Design Sync", "Mia Torres", 2026-11-12T11:00 → 12:00
- R3 Breeze, "Standup", "Liam Patel", 2026-11-12T09:30 → 09:45
- R4 Cove, "Focus Block", "Noah Kim", 2026-11-12T14:00 → 16:00
- R5 Dune, "Interview Loop", "Sofia Ross", 2026-11-13T10:00 → 12:00
- R6 Atlas, "Cancelled Planning", "Ava Chen", 2026-11-12T14:00 → 15:00,
  status `cancelled` (blocks nothing)

## 4. UI contract (single page `/`)

Header: application title **RoomReserve**; button **"New Reservation"**
(opens the form dialog).

Views/state:
- **Rooms panel**: list of rooms (name, capacity, floor). Selecting a
  room filters the reservation list. An "All rooms" reset control exists.
- **Date control**: `<input type="date">` labelled "Date"; the list shows
  reservations overlapping the chosen day; a "Clear date" control resets.
- **Availability filter**: controls "Free from"/"Free to"
  (`<input type="time">`); when set, the rooms panel highlights rooms
  with NO confirmed reservation overlapping that window
  (badge/text "Available" vs "Booked").
- **Reservation list**: table on desktop (Room, Title, Organizer, Start,
  End, Status, Actions); card list on mobile. Rows have **"Edit"** and
  **"Cancel"** controls. Cancel asks for confirmation ("Cancel this
  reservation?" Confirm/Keep). Cancelled rows show a **"Cancelled"**
  badge (visible when included via a "Show cancelled" toggle).
- **Form dialog** (create + edit): fields Room (select), Title (text),
  Organizer (text), Date (date), Start time (time), End time (time).
  Labels are exactly: "Room", "Title", "Organizer", "Date", "Start
  time", "End time". Submit button: **"Save Reservation"**. Inline
  validation messages for empty Title/Organizer. Server 409 renders
  "Time conflict with an existing reservation" inside the dialog.
- **States**: loading indicator during fetches; error panel with a
  **"Retry"** control on API failure; empty state "No reservations yet"
  with a call to action; no-match state "No reservations match" with a
  **"Clear filters"** control; empty rooms state "No rooms yet".
- **Accessibility & keyboard**: every control is reachable by Tab and
  operable by Enter/Space; dialog closes on Escape; inputs have
  associated labels; the Cancel confirm is keyboard-operable.
- **Responsive**: 1440×900 desktop layout; 390×844 and 320×700 mobile
  layouts with no horizontal overflow; sticky footer at bottom.

Visual identity: emerald/teal accent (distinct from StockPilot's neutral
and TaskFlow's teal-sidebar look), professional SaaS density, consistent
typography scale.

## 5. Frozen acceptance tests (committed with this spec)

- `apitest.mjs` — public API suite, 18 ordered checks (§2 behaviors:
  listing, filters, date search, validation order, conflict boundaries,
  cancellation semantics, edit re-validation, persistence across a dev
  server restart +2 checks).
- `uitest.mjs` — public UI suite, 20 checks (§4 behaviors incl. keyboard
  operability, conflict error rendering, availability filter, states).
- `heldout.mjs` — HELD-OUT suite, 12 checks, not visible to any track
  before scoring (boundary overlaps, cross-file persistence, idempotent
  cancel, filter combinations, malformed payloads).

## 6. Scoring

- Functional: public suites + held-out suite, per-check evidence.
- Visual: Session-034 evaluator, 10 metrics × 3 viewports (1440×900,
  390×844, 320×700).
- Provenance: per-file labels (QWEN-ORIGINAL / QWEN-REPAIRED /
  MIXED / TEACHER-INTEGRATION / TRUSTED-SCAFFOLD) — teacher bytes are
  never counted as model capability; L1/L2/L3/L4 repair provenance
  recorded per patch.
