// TRUSTED-SCAFFOLD (Session 036 harness): wipes Room/Reservation tables
// and re-seeds the SPEC §3 synthetic corpus. Test helper only — not part
// of the application under test.
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

const ROOMS = [
  ['Atlas Boardroom', 12, 3],
  ['Breeze Huddle', 4, 1],
  ['Cove Focus Room', 2, 2],
  ['Dune Workshop', 8, 3],
] as const

// [roomIdx, title, organizer, start, end, status]
const RESERVATIONS = [
  [0, 'Quarterly Review', 'Ava Chen', '2026-11-12T09:00', '2026-11-12T10:30', 'confirmed'],
  [0, 'Design Sync', 'Mia Torres', '2026-11-12T11:00', '2026-11-12T12:00', 'confirmed'],
  [1, 'Standup', 'Liam Patel', '2026-11-12T09:30', '2026-11-12T09:45', 'confirmed'],
  [2, 'Focus Block', 'Noah Kim', '2026-11-12T14:00', '2026-11-12T16:00', 'confirmed'],
  [3, 'Interview Loop', 'Sofia Ross', '2026-11-13T10:00', '2026-11-13T12:00', 'confirmed'],
  [0, 'Cancelled Planning', 'Ava Chen', '2026-11-12T14:00', '2026-11-12T15:00', 'cancelled'],
] as const

async function main() {
  try {
    await prisma.$executeRawUnsafe('DELETE FROM Reservation')
    await prisma.$executeRawUnsafe('DELETE FROM Room')
  } catch (e) {
    const msg = String(e)
    if (/no such table/i.test(msg)) {
      console.log('Room/Reservation tables do not exist yet — nothing to wipe')
      return
    }
    console.error('reseed wipe failed:', msg.slice(0, 200))
    process.exit(1)
  }
  const roomRows = []
  for (const [name, capacity, floor] of ROOMS) {
    roomRows.push(await prisma.room.create({
      data: { name, capacity, floor },
    }))
  }
  for (const [ri, title, organizer, start, end, status] of RESERVATIONS) {
    await prisma.reservation.create({
      data: {
        roomId: roomRows[ri].id, title, organizer, start,
        end, status,
      },
    })
  }
  console.log(`reseeded ${roomRows.length} rooms, ${RESERVATIONS.length} reservations`)
}

main().catch(e => { console.error(e); process.exit(1) })
  .finally(() => prisma.$disconnect())
