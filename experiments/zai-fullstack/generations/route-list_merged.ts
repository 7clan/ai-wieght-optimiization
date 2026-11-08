import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q')?.trim().toLowerCase() ?? ''
  const rows = await db.inventoryItem.findMany({
    where: q ? { OR: [{ name: { contains: q } }, { sku: { contains: q } }] } : {},
    orderBy: { updatedAt: 'desc' },
  })
  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const name = String(body.name ?? '').trim()
  const description = String(body.description ?? '').trim()
  const category = String(body.category ?? '').trim()
  const weight = Number(body.weight)
  const cost = Number(body.cost)
  const imageUrl = String(body.imageUrl ?? '').trim()
  const image = String(body.image ?? '').trim
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
    return NextResponse.json({ error: 'quantity must be 0-1000000' }, { status: 400 })
  }
  if (minQuantity < 0 || minQuantity > 100000) {
    return NextResponse.json({ error: 'minQuantity must be 0-100000' }, { status: 400 })
  }
  const row = await db.inventoryItem.create({
    data: {
      name,
      sku,
      quantity,
      minQuantity,
      category: body.category,
    },
  })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })
}
