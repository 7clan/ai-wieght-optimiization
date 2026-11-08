import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

type Params = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params
  const row = await db.inventoryItem.findUnique({ where: { id } })

  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })

  // Return the item in JSON
  return NextResponse.json({ item: { ...row, updatedAt:
    row.updatedAt.toISOString() } }, { status: 200 })
}

export async function PUT(req: NextRequest, { params }: Params) {
  // PUT BODY GENERATION FAILED (see generations/)
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id } = await params
  const ok = await db.inventoryItem.delete({ where: { id }
     }).then(() => true).catch(() => false)
  if (!ok) return NextResponse.json({ error: 'not found' },
     { status: 404 })
  return new NextResponse(null, { status: 204 })

  const { id } = await params
  const ok = await db.inventoryItem.delete({ where: { id }
     }).then(() => true).catch(() => false)
  if (!ok) return NextResponse.json({ error: 'not found' },
     { status: 404 })
  return new NextResponse(null, { status: 204 })

  const { id } = await params
}
