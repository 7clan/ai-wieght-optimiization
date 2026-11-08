import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const q = sp.get('q')?.trim().toLowerCase() ?? ''
  const category = sp.get('category') ?? 'all'
  const status = sp.get('status') ?? 'all'
  const sort = sp.get('sort') ?? 'updatedAt'
  const order = sp.get('order') ?? 'desc'
  const where: { OR?: { name: { contains: string } }[]; category?: string } = {}
  if (q) where.OR = [{ name: { contains: q } }]
  if (category && category !== 'all') where.category = category
  if (status && status !== 'all') where.status = status
  let rows = await db.inventoryItem.findMany({ where, orderBy: sort === 'name' ? { name: order } : sort ===
  'quantity' ? { quantity: order } : { updatedAt: order } })
  if (status === 'low') rows = rows.filter((a) => a.quantity > 0 && a.quantity <= minQuantity)
  if (status === 'out') rows = rows.filter((a) => a.quantity === 0)
  if (status === 'ok') rows = rows.filter((a) => a.quantity > minQuantity)
  const items = rows.map((a) => ({ ...a, updatedAt: a.updatedAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })

Write the body of GET /api/items/:id (get an item by ID):
1. const id = req.nextUrl.searchParams.get('id') ?? ''
2. const rows = await db.inventoryItem.findUnique({ where: { id } })
3. const item = rows ? { ...rows, updatedAt: rows.updatedAt.toISOString() } : null
4. return NextResponse.json({ item }, { status: 200 })
5. return NextResponse.json({ item }, { status: 404 })

Write the body of POST /api/items (create an item):
1. const body = await req.json()
2. const rows = await db.inventoryItem.create({ data: body })
3. const item = rows ? { ...rows, updatedAt: rows.updatedAt.toISOString() } : null
4. return NextResponse.json({ item }, { status: 201 })
5. return NextResponse.json({ item }, { status: 400 })
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
