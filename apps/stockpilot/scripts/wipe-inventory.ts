// TRUSTED-SCAFFOLD (Session 035 harness): wipes the InventoryItem table
// so the frozen acceptance tests start from a clean slate. Uses raw SQL
// so it works regardless of the generated Prisma client state, and is
// tolerant of the table not existing yet (Track A installs).
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

async function main() {
  try {
    const r = await prisma.$executeRawUnsafe('DELETE FROM InventoryItem')
    console.log(`wiped ${r} inventory rows`)
  } catch (e) {
    const msg = String(e)
    if (/no such table/i.test(msg)) {
      console.log('InventoryItem table does not exist yet — nothing to wipe')
    } else {
      console.error('wipe failed:', msg.slice(0, 200))
      process.exit(1)
    }
  } finally {
    await prisma.$disconnect()
  }
}

main()
