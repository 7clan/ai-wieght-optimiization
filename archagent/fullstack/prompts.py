"""Session 035 full-stack harness — prompt contracts.

Follows the frozen Session-034 discipline: every prompt contains ONLY
(a) a programming-concept explanation, (b) a worked example from a
DIFFERENT domain (never the target names), (c) measurable requirements,
(d) the anchor the model must continue from.  No teacher target code.

The TARGET is StockPilot (inventory management).  The DEMO domain is a
pet-shelter adoption registry — deliberately unrelated names, fields
and UI vocabulary.
"""
from __future__ import annotations

CONCEPT = """You write complete full-stack TypeScript for a Next.js 16
App Router application with Prisma + SQLite and REST API routes.
Every file is plain TypeScript or TSX. API handlers return JSON.
Numbers are validated integers; strings are trimmed and length-checked.
The UI uses React hooks and existing UI primitives (Button, Dialog,
Select, Input, Label, Table, Badge) imported from '@/components/ui/*'.
Write production-quality code with no placeholders or TODOs."""

# Different-domain worked example: pet shelter, NOT inventory.
DEMO_ROUTE = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for an API route file.  That task was "list + create
adoption records", and the correct answer was:

=== FILE: src/app/api/adoptions/route.ts ===
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const rows = await db.adoption.findMany({ orderBy: { updatedAt: 'desc' } })
  return NextResponse.json({ items: rows, total: rows.length })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const name = String(body.name ?? '').trim()
  if (!name || name.length > 60) {
    return NextResponse.json({ error: 'name is required (1-60 chars)' }, { status: 400 })
  }
  const age = Number(body.age)
  if (!Number.isInteger(age) || age < 0 || age > 40) {
    return NextResponse.json({ error: 'age must be an integer 0-40' }, { status: 400 })
  }
  const row = await db.adoption.create({
    data: { name, species: String(body.species ?? 'dog').trim(), age },
  })
  return NextResponse.json({ item: row }, { status: 201 })
}"""

DEMO_SCHEMA = """Example from a DIFFERENT app (the pet shelter),
showing the ANSWER FORMAT for the Prisma model block:

model Adoption {
  id         String   @id @default(cuid())
  name       String
  species    String
  age        Int
  updatedAt  DateTime @updatedAt
}"""


def track_a_prompt(spec_md: str) -> tuple[str, str]:
    """Monolithic unassisted baseline: whole application, one shot.
    Returns (prompt, anchor)."""
    parts = [CONCEPT, ""]
    parts.append(DEMO_ROUTE)
    parts.append("")
    parts.append("Now YOUR task.  Build this complete application.")
    parts.append("")
    parts.append(spec_md)
    parts.append("")
    parts.append("""OUTPUT FORMAT — write these four files, complete, in
this exact order, each introduced by its marker line:

=== FILE: prisma/schema.prisma (model block only) ===
=== FILE: src/app/api/items/route.ts ===
=== FILE: src/app/api/items/[id]/route.ts ===
=== FILE: src/app/page.tsx ===

prisma/schema.prisma contains ONLY the model block (the datasource is
already configured).  Start writing now, beginning with the marker
line:""")
    anchor = "=== FILE: prisma/schema.prisma (model block only) ===\n"
    parts.append(anchor)
    return "\n".join(parts), anchor
