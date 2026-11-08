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
  const row = await db.inventoryItem.update({ where: { id }, data: {
    name, category, sku, quantity, minQuantity
  } }).catch(() => null)
  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } })

And then the body:
  const { id } = await params
  const body = await req.json()
  const name = String(body.name ?? '').trim()
  const category = String(body.category ?? '').trim()
  const sku = String(body.sku ?? '').trim()
  const quantity = Number(body.quantity)
  const minQuantity = Number(body.minQuantity)
  const row = await db.inventoryItem.update({ where: { id }, data: {
    name, category, sku, quantity, minQuantity
  } }).catch(() => null)
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
