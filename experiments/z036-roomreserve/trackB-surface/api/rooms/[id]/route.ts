import { NextResponse } from 'next/server'

import { db } from '@/lib/db'

export async function GET(
  req: Request,
  { params }: { params: { id: string } },
) {
  const { id } = params
  const room = await db.room.findUnique({
    where: { id },
    include: { bookings: { orderBy: { start: 'desc' } } },
  })
  if (!room) {
    return NextResponse.json({ error: 'Room not found' }, { status: 404 })
  }
  return NextResponse.json(room)
}