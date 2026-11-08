"""SESSION 036 — RoomReserve generation contracts (TRUSTED-SCAFFOLD).

Small contracts for Track B (fixed ladder) and Track C (adaptive
controller).  Design rules distilled from the Session-035 capability
boundary findings:

  1. demos show the COMPLETE shape with neutral labels (demo-completeness
     law: the 1,000-token table contract landed first-sample while
     structural-only demos failed 12/12);
  2. specs are code-shaped actions ("set X to Y", "call Z") — never prose
     that can leak verbatim into code;
  3. expectations are AST-level (handlers/calls/accesses/exprs/uiStrings)
     — verified by archagent/verify, never substrings;
  4. the overlap logic is split into its own body contract with a
     different-domain demo (hotel spa bookings, not meeting rooms) so the
     model must adapt the pattern, not copy domain fields.
"""
from __future__ import annotations

CONCEPT = ("You are writing RoomReserve, a Next.js 16 meeting-room "
           "reservation app. TypeScript, Prisma + SQLite, NextResponse "
           "JSON APIs. Dates are plain ISO strings 'YYYY-MM-DDTHH:mm' "
           "compared lexicographically.")

# ---------------------------------------------------------------- schema

SCHEMA_CONTRACT = {
    "key": "schema",
    "file": "prisma/schema.prisma",
    "kind": "prisma",
    "demo": (
        "model FitnessClass {\n"
        "  id        String  @id @default(cuid())\n"
        "  title     String\n"
        "  coach     String\n"
        "  startHour Int\n"
        "  active    Boolean @default(true)\n"
        "}\n"),
    "spec": ("Add two models to the schema file. Model Room: fields "
             "id String @id @default(cuid()), name String, capacity Int, "
             "floor Int, createdAt DateTime @default(now()); add relation "
             "field reservations Reservation[]. Model Reservation: fields "
             "id String @id @default(cuid()), roomId String, title String, "
             "organizer String, start String, end String, status String "
             "@default(\"confirmed\"), createdAt DateTime @default(now()); "
             "add relation field room Room @relation(fields: [roomId], "
             "references: [id]). Keep the existing User and Post models "
             "and the generator/datasource blocks unchanged."),
    "anchor": "model Room {",
    "max_tokens": 420,
    "expect": {
        "kind": "prisma",
        "models": [
            {"name": "Room", "fields": [
                {"name": "id", "type": "String", "attrsIncludes": ["@id"]},
                {"name": "name", "type": "String"},
                {"name": "capacity", "type": "Int"},
                {"name": "floor", "type": "Int"},
                {"name": "reservations", "type": "Reservation", "isList": True},
            ]},
            {"name": "Reservation", "fields": [
                {"name": "roomId", "type": "String"},
                {"name": "title", "type": "String"},
                {"name": "organizer", "type": "String"},
                {"name": "start", "type": "String"},
                {"name": "end", "type": "String"},
                {"name": "status", "type": "String"},
                {"name": "room", "type": "Room"},
            ]},
        ],
    },
}

# ---------------------------------------------------------------- types

TYPES_CONTRACT = {
    "key": "types",
    "file": "src/lib/roomreserve/types.ts",
    "kind": "types",
    "demo": (
        "// types for a gym booking board\n"
        "export interface Court {\n"
        "  id: string\n"
        "  name: string\n"
        "  capacity: number\n"
        "}\n\n"
        "export interface Lesson {\n"
        "  id: string\n"
        "  courtId: string\n"
        "  coach: string\n"
        "  start: string\n"
        "  end: string\n"
        "  status: 'booked' | 'waitlist'\n"
        "  courtName: string\n"
        "}\n"),
    "spec": ("Write the file with two exported interfaces. Interface "
             "Room: members id string, name string, capacity number, "
             "floor number. Interface Reservation: members id string, "
             "roomId string, title string, organizer string, start "
             "string, end string, status string, roomName string."),
    "anchor": "export interface Room {",
    "max_tokens": 300,
    "expect": {
        "kind": "types",
        "interfaces": [
            {"name": "Room", "members": {
                "id": "string", "name": "string",
                "capacity": "number", "floor": "number"}},
            {"name": "Reservation", "members": {
                "id": "string", "roomId": "string", "title": "string",
                "organizer": "string", "start": "string", "end": "string",
                "status": "string", "roomName": "string"}},
        ],
    },
}

# ------------------------------------------------------- rooms route

ROOMS_ROUTE_CONTRACT = {
    "key": "rooms-route",
    "file": "src/app/api/rooms/route.ts",
    "kind": "route",
    "demo": (
        "// a library study-desk listing route (different domain)\n"
        "import { NextRequest, NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "export async function GET(req: NextRequest) {\n"
        "  const q = req.nextUrl.searchParams.get('q')?.toLowerCase() ?? ''\n"
        "  const minSeats = Number(req.nextUrl.searchParams.get('minSeats') ?? 0)\n"
        "  const where: { name?: { contains: string } } = {}\n"
        "  if (q) where.name = { contains: q }\n"
        "  let rows = await db.desk.findMany({ where, orderBy: { name: 'asc' } })\n"
        "  if (minSeats > 0) rows = rows.filter((d) => d.seats >= minSeats)\n"
        "  return NextResponse.json({ desks: rows, total: rows.length })\n"
        "}\n"),
    "spec": ("Write the rooms list route. Export GET. Read query params q "
             "and minCapacity. Build where object with name contains when "
             "q is set. Call db.room.findMany with where and orderBy name "
             "asc. Filter rows by capacity at least minCapacity when it is "
             "above zero. Return NextResponse.json with rooms and total."),
    "anchor": "import { NextRequest, NextResponse } from 'next/server'",
    "max_tokens": 420,
    "expect": {
        "kind": "route",
        "file": "src/app/api/rooms/route.ts",
        "handlers": ["GET"],
        "calls": ["NextResponse.json", "db.room.findMany"],
        "accesses": ["req.nextUrl.searchParams"],
    },
}

# --------------------------------------------------- rooms [id] route

ROOM_ID_ROUTE_CONTRACT = {
    "key": "room-id-route",
    "file": "src/app/api/rooms/[id]/route.ts",
    "kind": "route",
    "demo": (
        "// a library desk detail route (different domain)\n"
        "import { NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "export async function GET(\n"
        "  _req: Request,\n"
        "  { params }: { params: Promise<{ id: string }> },\n"
        ") {\n"
        "  const { id } = await params\n"
        "  const desk = await db.desk.findUnique({\n"
        "    where: { id },\n"
        "    include: { bookings: { orderBy: { start: 'desc' } } },\n"
        "  })\n"
        "  if (!desk) {\n"
        "    return NextResponse.json({ error: 'Desk not found' }, { status: 404 })\n"
        "  }\n"
        "  return NextResponse.json({ desk })\n"
        "}\n"),
    "spec": ("Write the room detail route. Export GET taking params "
             "Promise with id. Await params. Call db.room.findUnique "
             "with where id and include reservations ordered by start "
             "desc. When the room is missing return NextResponse.json "
             "with error 'Room not found' and status 404. Otherwise "
             "return NextResponse.json with room."),
    "anchor": "import { NextResponse } from 'next/server'",
    "max_tokens": 360,
    "expect": {
        "kind": "route",
        "file": "src/app/api/rooms/[id]/route.ts",
        "handlers": ["GET"],
        "calls": ["NextResponse.json", "db.room.findUnique"],
    },
}

# --------------------------------------------- reservations route (GET+POST)

RESERVATIONS_ROUTE_CONTRACT = {
    "key": "reservations-route",
    "file": "src/app/api/reservations/route.ts",
    "kind": "route",
    "demo": (
        "// a hotel spa treatment booking route (different domain)\n"
        "import { NextRequest, NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "export async function GET(req: NextRequest) {\n"
        "  const sp = req.nextUrl.searchParams\n"
        "  const guest = sp.get('guest')?.toLowerCase() ?? ''\n"
        "  const day = sp.get('day') ?? ''\n"
        "  const where: { status: string; OR?: { title: { contains: string } }[] } "
        "  = { status: 'booked' }\n"
        "  if (guest) where.OR = [{ title: { contains: guest } }]\n"
        "  let rows = await db.treatment.findMany({ where, orderBy: { start: 'asc' } })\n"
        "  if (day) {\n"
        "    const dayStart = `${day}T00:00`\n"
        "    const dayEnd = `${day}T23:59`\n"
        "    rows = rows.filter((t) => t.start <= dayEnd && t.end > dayStart)\n"
        "  }\n"
        "  const items = rows.map((t) => ({ ...t, stylist: t.stylist ?? 'spa' }))\n"
        "  return NextResponse.json({ treatments: items, total: items.length })\n"
        "}\n\n"
        "export async function POST(req: NextRequest) {\n"
        "  const body = await req.json()\n"
        "  const title = String(body.title ?? '').trim()\n"
        "  if (!title) {\n"
        "    return NextResponse.json({ error: 'Title is required' }, { status: 400 })\n"
        "  }\n"
        "  const suite = await db.suite.findUnique({ where: { id: body.suiteId } })\n"
        "  if (!suite) {\n"
        "    return NextResponse.json({ error: 'Suite not found' }, { status: 404 })\n"
        "  }\n"
        "  const clash = await db.treatment.findFirst({\n"
        "    where: { suiteId: suite.id, status: 'booked', start: { lt: body.end }, "
        "end: { gt: body.start } },\n"
        "  })\n"
        "  if (clash) {\n"
        "    return NextResponse.json({ error: 'Time conflict with an existing "
        "treatment' }, { status: 409 })\n"
        "  }\n"
        "  const created = await db.treatment.create({\n"
        "    data: { suiteId: suite.id, title, guest: body.guest, "
        "start: body.start, end: body.end, status: 'booked' },\n"
        "  })\n"
        "  return NextResponse.json({ treatment: created }, { status: 201 })\n"
        "}\n"),
    "spec": ("Write the reservations route with GET and POST. GET: read "
             "q, date, roomId, includeCancelled from searchParams. Default "
             "where status confirmed. When q set, where OR title contains "
             "q. Call db.reservation.findMany with where ordered by start "
             "asc, include room relation. When date set filter rows with "
             "start at or before date T23:59 and end after date T00:00. "
             "When roomId set filter rows by roomId equal. When "
             "includeCancelled is 1 fetch without the status filter. Map "
             "rows to spread the row plus roomName from room.name. Return "
             "NextResponse.json with reservations and total. POST: await "
             "req.json. Trim title with String; when empty return 400 'Title "
             "is required'. Trim organizer the same way; when empty return "
             "400 'Organizer is required'. Call db.room.findUnique where "
             "id body.roomId; when missing return 404 'Room not found'. "
             "Validate start and end with regex /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:"
             "\\d{2}$/; when either fails return 400 'Invalid date format'. "
             "When start is not before end return 400 'End must be after "
             "start'. Call db.reservation.findFirst where roomId equal, "
             "status confirmed, start lt body.end, end gt body.start. When "
             "a clash exists return 409 'Time conflict with an existing "
             "reservation'. Call db.reservation.create with data roomId, "
             "title, organizer, start, end, status confirmed. Return "
             "NextResponse.json with reservation and status 201."),
    "anchor": "import { NextRequest, NextResponse } from 'next/server'",
    "max_tokens": 900,
    "expect": {
        "kind": "route",
        "file": "src/app/api/reservations/route.ts",
        "handlers": ["GET", "POST"],
        "calls": ["NextResponse.json", "db.reservation.findMany",
                  "db.reservation.findFirst", "db.reservation.create",
                  "db.room.findUnique"],
        "exprs": [],
    },
}

# ------------------------------------------- reservations [id] route

RESERVATION_ID_ROUTE_CONTRACT = {
    "key": "reservation-id-route",
    "file": "src/app/api/reservations/[id]/route.ts",
    "kind": "route",
    "demo": (
        "// a spa treatment edit/cancel route (different domain)\n"
        "import { NextRequest, NextResponse } from 'next/server'\n"
        "import { db } from '@/lib/db'\n\n"
        "export async function PUT(\n"
        "  req: NextRequest,\n"
        "  { params }: { params: Promise<{ id: string }> },\n"
        ") {\n"
        "  const { id } = await params\n"
        "  const body = await req.json()\n"
        "  const existing = await db.treatment.findUnique({ where: { id } })\n"
        "  if (!existing) {\n"
        "    return NextResponse.json({ error: 'Treatment not found' }, { status: 404 })\n"
        "  }\n"
        "  const start = body.start ?? existing.start\n"
        "  const end = body.end ?? existing.end\n"
        "  if (start >= end) {\n"
        "    return NextResponse.json({ error: 'End must be after start' }, { status: 400 })\n"
        "  }\n"
        "  const clash = await db.treatment.findFirst({\n"
        "    where: { suiteId: existing.suiteId, status: 'booked', "
        "start: { lt: end }, end: { gt: start }, id: { not: id } },\n"
        "  })\n"
        "  if (clash) {\n"
        "    return NextResponse.json({ error: 'Time conflict with an existing "
        "treatment' }, { status: 409 })\n"
        "  }\n"
        "  const updated = await db.treatment.update({\n"
        "    where: { id },\n"
        "    data: { title: body.title ?? existing.title, start, end },\n"
        "  })\n"
        "  return NextResponse.json({ treatment: updated })\n"
        "}\n\n"
        "export async function DELETE(\n"
        "  _req: Request,\n"
        "  { params }: { params: Promise<{ id: string }> },\n"
        ") {\n"
        "  const { id } = await params\n"
        "  const existing = await db.treatment.findUnique({ where: { id } })\n"
        "  if (!existing) {\n"
        "    NextResponse.json({ error: 'Treatment not found' }, { status: 404 })\n"
        "    return\n"
        "  }\n"
        "  const cancelled = await db.treatment.update({\n"
        "    where: { id },\n"
        "    data: { status: 'cancelled' },\n"
        "  })\n"
        "  return NextResponse.json({ treatment: cancelled })\n"
        "}\n"),
    "spec": ("Write the reservation detail route with PUT and DELETE. "
             "PUT: await params id and req.json. Find the reservation "
             "with db.reservation.findUnique where id; when missing "
             "return 404 'Reservation not found'. Merge start and end "
             "from body with ?? existing values. When start is not "
             "before end return 400 'End must be after start'. Find a "
             "clash with db.reservation.findFirst where roomId equal to "
             "the reservation roomId, status confirmed, start lt end, "
             "end gt start, id not equal to id. When a clash exists "
             "return 409 'Time conflict with an existing reservation'. "
             "Update with db.reservation.update where id, data title "
             "body.title ?? existing.title, organizer body.organizer ?? "
             "existing.organizer, start, end. Return NextResponse.json "
             "with reservation. DELETE: await params id. Find with "
             "db.reservation.findUnique; when missing return 404 "
             "'Reservation not found'. Update with db.reservation.update "
             "where id data status cancelled. Return NextResponse.json "
             "with reservation."),
    "anchor": "import { NextRequest, NextResponse } from 'next/server'",
    "max_tokens": 700,
    "expect": {
        "kind": "route",
        "file": "src/app/api/reservations/[id]/route.ts",
        "handlers": ["PUT", "DELETE"],
        "calls": ["NextResponse.json", "db.reservation.findUnique",
                  "db.reservation.findFirst", "db.reservation.update"],
    },
}

# ------------------------------------------------------- UI contracts

STATES_CONTRACT = {
    "key": "states",
    "file": "src/components/roomreserve/states.tsx",
    "kind": "component",
    "demo": (
        "// empty/error/no-match states for a plant-watering app\n"
        "export function EmptyState({ onAdd }: { onAdd: () => void }) {\n"
        "  return (\n"
        "    <div className=\"flex flex-col items-center gap-3 py-16 text-center\">\n"
        "      <p className=\"text-base font-medium\">No plants yet</p>\n"
        "      <p className=\"text-sm text-muted-foreground\">Add your first plant to start tracking.</p>\n"
        "      <button onClick={onAdd} className=\"mt-2\">Add Plant</button>\n"
        "    </div>\n"
        "  )\n"
        "}\n\n"
        "export function ErrorState({ message, onRetry }: "
        "{ message: string; onRetry: () => void }) {\n"
        "  return (\n"
        "    <div className=\"flex flex-col items-center gap-3 py-16 text-center\">\n"
        "      <p className=\"text-base font-medium\">Something went wrong</p>\n"
        "      <p className=\"text-sm text-muted-foreground\">{message}</p>\n"
        "      <button onClick={onRetry} className=\"mt-2\">Retry</button>\n"
        "    </div>\n"
        "  )\n"
        "}\n"),
    "spec": ("Write the states file with three exported components. "
             "EmptyState takes onAdd and shows the text 'No reservations "
             "yet', a smaller hint 'Create your first reservation to get "
             "started.', and a button 'New Reservation' calling onAdd. "
             "ErrorState takes message and onRetry and shows 'Something "
             "went wrong', the message, and a button 'Retry' calling "
             "onRetry. NoMatchesState takes onClear and shows 'No "
             "reservations match' and a button 'Clear filters' calling "
             "onClear."),
    "anchor": "export function EmptyState(",
    "max_tokens": 520,
    "expect": {
        "kind": "component",
        "file": "src/components/roomreserve/states.tsx",
        "exports": ["EmptyState", "ErrorState", "NoMatchesState"],
        "uiStrings": ["No reservations yet", "Retry", "No reservations match",
                      "Clear filters"],
        "calls": [],
    },
}

ROOM_PANEL_CONTRACT = {
    "key": "room-panel",
    "file": "src/components/roomreserve/room-panel.tsx",
    "kind": "component",
    "demo": (
        "// a workshop-tools picker panel (different domain)\n"
        "export function ToolPanel({ tools, selectedId, onSelect }: {\n"
        "  tools: { id: string; label: string; slots: number }[]\n"
        "  selectedId: string\n"
        "  onSelect: (id: string) => void\n"
        "}) {\n"
        "  return (\n"
        "    <aside className=\"w-56 shrink-0\">\n"
        "      <h2 className=\"mb-3 text-sm font-medium\">Tools</h2>\n"
        "      <button onClick={() => onSelect('')}>All tools</button>\n"
        "      <ul className=\"space-y-1\">\n"
        "        {tools.map((t) => (\n"
        "          <li key={t.id}>\n"
        "            <button\n"
        "              aria-pressed={selectedId === t.id}\n"
        "              onClick={() => onSelect(t.id)}\n"
        "              className={selectedId === t.id ? 'bg-accent' : ''}\n"
        "            >\n"
        "              <span>{t.label}</span>\n"
        "              <span className=\"text-xs text-muted-foreground\">"
              "{t.slots} slots</span>\n"
        "            </button>\n"
        "          </li>\n"
        "        ))}\n"
        "      </ul>\n"
        "    </aside>\n"
        "  )\n"
        "}\n"),
    "spec": ("Write the room panel component. Export RoomPanel taking "
             "props rooms with id name capacity floor, selectedId string, "
             "onSelect function taking string, availability map from id to "
             "boolean. Render an aside with heading 'Rooms', a button 'All "
             "rooms' calling onSelect with empty string, and a list of "
             "buttons per room showing the room name, a span with capacity "
             "and ' seats' and floor 'F' plus the floor number. Set "
             "aria-pressed to whether the room is selected. When the "
             "availability map has an entry for the room render a span "
             "'Available' when true else 'Booked'."),
    "anchor": "export function RoomPanel(",
    "max_tokens": 620,
    "expect": {
        "kind": "component",
        "file": "src/components/roomreserve/room-panel.tsx",
        "exports": ["RoomPanel"],
        "uiStrings": ["All rooms", "Available", "Booked", "Rooms"],
    },
}

RESERVATION_TABLE_CONTRACT = {
    "key": "reservation-table",
    "file": "src/components/roomreserve/reservation-table.tsx",
    "kind": "component",
    "demo": (
        "// a deliveries table with desktop table + mobile cards\n"
        "export function DeliveryTable({ rows, onEdit, onCancel }: {\n"
        "  rows: { id: string; vendor: string; item: string; "
        "eta: string; status: string }[]\n"
        "  onEdit: (id: string) => void\n"
        "  onCancel: (id: string) => void\n"
        "}) {\n"
        "  return (\n"
        "    <div>\n"
        "      <table className=\"hidden w-full text-sm md:table\">\n"
        "        <thead><tr><th>Vendor</th><th>Item</th><th>ETA</th>"
        "<th>Status</th><th>Actions</th></tr></thead>\n"
        "        <tbody>\n"
        "          {rows.map((r) => (\n"
        "            <tr key={r.id}>\n"
        "              <td>{r.vendor}</td><td>{r.item}</td><td>{r.eta}</td>\n"
        "              <td><span>{r.status}</span></td>\n"
        "              <td>\n"
        "                <button onClick={() => onEdit(r.id)}>Edit</button>\n"
        "                <button onClick={() => onCancel(r.id)}>Cancel</button>\n"
        "              </td>\n"
        "            </tr>\n"
        "          ))}\n"
        "        </tbody>\n"
        "      </table>\n"
        "      <ul className=\"space-y-2 md:hidden\">\n"
        "        {rows.map((r) => (\n"
        "          <li key={r.id} className=\"rounded-md border p-3\">\n"
        "            <p className=\"font-medium\">{r.item}</p>\n"
        "            <p className=\"text-sm text-muted-foreground\">{r.vendor}"
        " · {r.eta}</p>\n"
        "            <div className=\"mt-2 flex gap-2\">\n"
        "              <button onClick={() => onEdit(r.id)}>Edit</button>\n"
        "              <button onClick={() => onCancel(r.id)}>Cancel</button>\n"
        "            </div>\n"
        "          </li>\n"
        "        ))}\n"
        "      </ul>\n"
        "    </div>\n"
        "  )\n"
        "}\n"),
    "spec": ("Write the reservation list component. Export "
             "ReservationTable taking props rows of reservations with id "
             "roomName title organizer start end status, onEdit and onCancel "
             "functions taking string. Render a desktop table hidden below "
             "md with headers Room, Title, Organizer, Start, End, Status, "
             "Actions and one row per reservation; each row shows the "
             "fields, a status span, an 'Edit' button calling onEdit with "
             "the id and a 'Cancel' button calling onCancel with the id. "
             "Render a mobile card list hidden at md and above with the "
             "title, a line with roomName, start and end, and the same two "
             "buttons."),
    "anchor": "export function ReservationTable(",
    "max_tokens": 700,
    "expect": {
        "kind": "component",
        "file": "src/components/roomreserve/reservation-table.tsx",
        "exports": ["ReservationTable"],
        "uiStrings": ["Edit", "Cancel"],
    },
}

RESERVATION_FORM_CONTRACT = {
    "key": "reservation-form",
    "file": "src/components/roomreserve/reservation-form.tsx",
    "kind": "component",
    "demo": (
        "// a course-registration dialog form (different domain)\n"
        "export function SignupForm({ open, onClose }: {\n"
        "  open: boolean\n"
        "  onClose: () => void\n"
        "}) {\n"
        "  return (\n"
        "    <div role=\"dialog\" aria-modal=\"true\" hidden={!open}>\n"
        "      <div>\n"
        "        <label htmlFor=\"f-title\">Course</label>\n"
        "        <input id=\"f-title\" />\n"
        "        <label htmlFor=\"f-coach\">Coach</label>\n"
        "        <input id=\"f-coach\" />\n"
        "        <label htmlFor=\"f-day\">Day</label>\n"
        "        <input id=\"f-day\" type=\"date\" />\n"
        "        <label htmlFor=\"f-from\">From</label>\n"
        "        <input id=\"f-from\" type=\"time\" />\n"
        "        <label htmlFor=\"f-to\">To</label>\n"
        "        <input id=\"f-to\" type=\"time\" />\n"
        "        <button type=\"submit\">Save Signup</button>\n"
        "      </div>\n"
        "    </div>\n"
        "  )\n"
        "}\n"),
    "spec": ("Write the reservation form dialog component. Export "
             "ReservationForm taking props open boolean, rooms list with "
             "id and name, initial values with roomId title organizer date "
             "start end, errorText string, onSubmit function taking the "
             "form values, onClose function. Render a div with role dialog "
             "and aria-modal, hidden when not open, closing on Escape via "
             "onKeyDown. Fields with labels 'Room' as a select of rooms, "
             "'Title', 'Organizer', 'Date' type date, 'Start time' type "
             "time, 'End time' type time. A 'Save Reservation' submit "
             "button calls onSubmit with the field values. When errorText "
             "is set render it in a red-ish paragraph inside the dialog."),
    "anchor": "export function ReservationForm(",
    "max_tokens": 760,
    "expect": {
        "kind": "component",
        "file": "src/components/roomreserve/reservation-form.tsx",
        "exports": ["ReservationForm"],
        "uiStrings": ["Save Reservation"],
    },
}

HOOK_CONTRACT = {
    "key": "hook",
    "file": "src/lib/roomreserve/use-reservations.ts",
    "kind": "hook",
    "demo": (
        "// a live-feed data hook for a cycling club (different domain)\n"
        "'use client'\n"
        "import { useCallback, useEffect, useState } from 'react'\n\n"
        "export function useRides() {\n"
        "  const [rides, setRides] = useState([])\n"
        "  const [loading, setLoading] = useState(true)\n"
        "  const [error, setError] = useState('')\n"
        "  const [reloadKey, setReloadKey] = useState(0)\n\n"
        "  useEffect(() => {\n"
        "    let alive = true\n"
        "    setLoading(true)\n"
        "    fetch('/api/rides')\n"
        "      .then((r) => (r.ok ? r.json() : Promise.reject('load failed')))\n"
        "      .then((d) => { if (alive) { setRides(d.rides ?? []); "
        "setError('') } })\n"
        "      .catch(() => { if (alive) setError('Could not load rides') })\n"
        "      .finally(() => { if (alive) setLoading(false) })\n"
        "    return () => { alive = false }\n"
        "  }, [reloadKey])\n\n"
        "  const reload = useCallback(() => setReloadKey((k) => k + 1), [])\n"
        "  return { rides, loading, error, reload }\n"
        "}\n"),
    "spec": ("Write the data hook. Export useReservations taking a params "
             "object with date string, roomId string, includeCancelled "
             "boolean. State: reservations array, rooms array, loading "
             "boolean, error string, reloadKey number. Effect on reloadKey "
             "and params: set loading true, fetch '/api/rooms' and "
             "'/api/reservations' with URLSearchParams of the params, set "
             "state from the JSON responses, on failure set error 'Could "
             "not load reservations', finally set loading false with an "
             "alive guard. Expose reload with useCallback incrementing "
             "reloadKey. Return object with rooms, reservations, loading, "
             "error, reload."),
    "anchor": "'use client'",
    "max_tokens": 640,
    "expect": {
        "kind": "hook",
        "file": "src/lib/roomreserve/use-reservations.ts",
        "exports": ["useReservations"],
        "calls": ["fetch", "useEffect", "useState", "useCallback"],
    },
}

PAGE_CONTRACT = {
    "key": "page",
    "file": "src/app/page.tsx",
    "kind": "page",
    "demo": (
        "// an assembly page for a bookshelf app (shape reference)\n"
        "import { useBooks } from '@/lib/bookshelf/use-books'\n"
        "import { BookTable } from '@/components/bookshelf/book-table'\n\n"
        "export default function Home() {\n"
        "  const { books, loading, error, reload } = useBooks()\n"
        "  return (\n"
        "    <div className=\"min-h-screen\">\n"
        "      <header><h1>Bookshelf</h1></header>\n"
        "      <main>{books.length > 0 ? <BookTable rows={books} /> : null}</main>\n"
        "      <footer>Library demo</footer>\n"
        "    </div>\n"
        "  )\n"
        "}\n"),
    "spec": ("Write the page. Default export component Home. Header with "
             "h1 'RoomReserve' and a 'New Reservation' button. Main "
             "section using useReservations, rendering the room panel, a "
             "date input labelled 'Date' with a 'Clear date' button, time "
             "inputs 'Free from' and 'Free to' for availability, a 'Show "
             "cancelled' toggle, and the reservation table. Loading, "
             "error and empty states from the states file. Footer with "
             "'RoomReserve — plan and book rooms'."),
    "anchor": "import { useReservations } from '@/lib/roomreserve/use-reservations'",
    "max_tokens": 900,
    "expect": {
        "kind": "page",
        "file": "src/app/page.tsx",
        "exports": ["default"],
        "uiStrings": ["RoomReserve", "New Reservation", "Clear date",
                      "Show cancelled"],
        "accesses": ["useReservations"],
    },
}

ALL_CONTRACTS = [SCHEMA_CONTRACT, TYPES_CONTRACT, ROOMS_ROUTE_CONTRACT,
                 ROOM_ID_ROUTE_CONTRACT, RESERVATIONS_ROUTE_CONTRACT,
                 RESERVATION_ID_ROUTE_CONTRACT, STATES_CONTRACT,
                 ROOM_PANEL_CONTRACT, RESERVATION_TABLE_CONTRACT,
                 RESERVATION_FORM_CONTRACT, HOOK_CONTRACT, PAGE_CONTRACT]
