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
  const { id } = await params
  const body = await req.json()
  const name = String(body.name ?? '').trim()
  const category = String(body.category ?? '').trim()
  const sku = String(body.sku ?? '').trim()
  const quantity = Number(body.quantity)
  const minQuantity = Number(body.minQuantity)
  if (name.length < 1 || name.length > 80) {
    return NextResponse.json({ error: 'name is required (1-80 chars)' }, { status: 400 })
  }
  if (category.length < 1 || category.length > 40) {
    return NextResponse.json({ error: 'category is required (1-40 chars)' }, { status: 400 })
  }
  if (sku.length < 1 || sku.length > 40) {
    return NextResponse.json({ error: 'sku is required (1-40 chars)' }, { status: 400 })
  }
  if (quantity < 0 || quantity > 1000000) {
If you need to check if the quantity is an integer, use the !Number.isInteger() operator.
}
  if (minQuantity < 0 || minQuantity > 1000000) {
    return NextResponse.json({ error: 'minQuantity must be an integer 0-1000000' }, { status: 400 })
  }
  const row = await db.inventoryItem.update({ where: { id }, data: { name, category, sku, quantity, minQuantity } }).catch(() => null)
  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } })
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id } = await params
  const ok = await db.inventoryItem.delete({ where: { id }
     }).then(() => true).catch(() => false)
  if (!ok) return NextResponse.json({ error: 'not found' },
     { status: 404 })
  return new NextResponse(null, { status: 204 })
}
