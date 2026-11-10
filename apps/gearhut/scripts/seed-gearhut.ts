// SESSION040 GearHut seed — TRUSTED-SCAFFOLD (demo data, not model output).
// Idempotent: wipes gear tables and reseeds the frozen demo dataset.
import { PrismaClient } from '@prisma/client'

const db = new PrismaClient()

async function main() {
  await db.gearItem.deleteMany()
  await db.gearLocker.deleteMany()

  const mainLocker = await db.gearLocker.create({
    data: { id: 'locker-main', name: 'Main locker' },
  })
  const crate = await db.gearLocker.create({
    data: { id: 'locker-expedition', name: 'Expedition crate' },
  })

  await db.gearItem.createMany({
    data: [
      { label: 'Aurora tent', usageHours: 0, status: 'stashed', lockerId: mainLocker.id },
      { label: 'Summit stove', usageHours: 340, status: 'retired', lockerId: mainLocker.id },
      { label: 'Terra 40 backpack', usageHours: 120, status: 'inspected', lockerId: mainLocker.id },
      { label: 'Canyon rope 60m', usageHours: 45, status: 'stashed', lockerId: crate.id },
      { label: 'Fjord sleeping bag', usageHours: 88, status: 'inspected', lockerId: crate.id },
      { label: 'Mesa headlamp', usageHours: 12, status: 'stashed', lockerId: crate.id },
    ],
  })

  const count = await db.gearItem.count()
  console.log(`Seeded ${count} gear items in 2 lockers`)
}

main().catch((error) => { console.error(error); process.exit(1) }).finally(() => db.$disconnect())
