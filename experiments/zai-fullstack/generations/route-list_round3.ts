import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  // GET BODY GENERATION FAILED ROUND 3
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

  const row = await db.inventoryItem.create({ data: { name, category, sku, quantity, minQuantity } })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })
}
