import { NextRequest, NextResponse } from 'next/server'
 
import { db } from '@/lib/db'

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const body = await req.json()
  const existing = await db.reservation.findUnique({ where: { id } })
  if (!existing) {
    return NextResponse.json({ error: 'Reservation not found' }, { status: 404 })
  }
  const start = body.start ?? existing.start
  const end = body.end ?? existing.end
  if (start >= end) {
    return NextResponse.json({ error: 'End must be after start' }, { status: 400 })
  }
  const clash = await db.reservation.findFirst({
    where: { roomId: existing.roomId, status: 'confirmed', start: { lt: end }, end: { gt: start }, id: { not: id } },
  })
  if (clash) {
    return NextResponse.json({ error: 'Time conflict with an existing reservation' }, { status: 409 })
  }
  const updated = await db.reservation.update({
    where: { id },
    data: { title: body.title ?? existing.title, start, end },
  })
  return NextResponse.json({ reservation: updated })
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const existing = await db.reservation.findUnique({ where: { id } })
  if (!existing) {
    NextResponse.json({ error: 'Reservation not found' }, { status: 404 })
    return
  }
  const cancelled = await db.reservation.update({
    where: { id },
    data: { status: 'cancelled' },
  })
  return NextResponse.json({ reservation: cancelled })
}