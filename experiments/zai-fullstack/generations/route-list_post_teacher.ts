import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams
  const q = sp.get('q')?.trim().toLowerCase() ?? ''
  const category = sp.get('category') ?? 'all'
  const status = sp.get('status') ?? 'all'
  const sort = sp.get('sort') ?? 'updatedAt'
  const order = sp.get('order') ?? 'desc'
  const where: { OR?: { name: { contains: string } }[] } = {}
  if (q) where.OR = [{ name: { contains: q } }]
  if (category && category !== 'all') where.category = category
  let rows = await db.inventoryItem.findMany({ where, orderBy: sort === 'name' ? { name: order } : sort ===
  'quantity' ? { quantity: order } : { updatedAt: order } })
  if (status === 'low') rows = rows.filter((a) => a.quantity > 0 && a.quantity <= a.minQuantity)
  if (status === 'out') rows = rows.filter((a) => a.quantity === 0)
  if (status === 'ok') rows = rows.filter((a) => a.quantity > a.minQuantity)
  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })
}

export async function POST(req: NextRequest) {
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
  if (sku.length > 40) {
    return NextResponse.json({ error: 'sku is too long (40 chars)' }, { status: 400 })
  }
  if (!Number.isInteger(quantity) || quantity < 0 || quantity > 1000000) {
    return NextResponse.json({ error: 'quantity must be an integer 0-1000000' }, { status: 400 })
  }
  if (!Number.isInteger(minQuantity) || minQuantity < 0 || minQuantity > 1000000) {
    return NextResponse.json({ error: 'minQuantity must be an integer 0-1000000' }, { status: 400 })
  }

  const row = await db.inventoryItem.create({ data: { name, category, sku: sku || null, quantity, minQuantity } })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })
}
