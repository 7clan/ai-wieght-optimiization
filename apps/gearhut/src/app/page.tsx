// SESSION040 GearHut — attribution: TEACHER-INTEGRATED (frozen spec §ui_contract
// teacher_assembly). This server component loads lockers and the full item
// list from the database and assembles the two Qwen-generated surfaces:
// the manager (integration skill) and the quick-filter list (react skill).

import GearItemManager from '@/components/gearhut/gear-item-manager'
import GearItemList from '@/components/gearhut/gear-item-list'
import { db } from '@/lib/db'

export const dynamic = 'force-dynamic'

export default async function Home() {
  const lockers = await db.gearLocker.findMany({
    orderBy: { id: 'asc' },
    select: { id: true, name: true },
  })
  const allGear = await db.gearItem.findMany({
    orderBy: { label: 'asc' },
    select: { id: true, label: true, usageHours: true, status: true },
  })

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="grid size-9 place-items-center rounded-lg bg-emerald-600 text-lg text-white">
              ⛰
            </span>
            <div>
              <h1 className="text-lg font-semibold leading-tight">GearHut</h1>
              <p className="text-xs text-muted-foreground">Gear locker maintenance log</p>
            </div>
          </div>
          <p className="hidden text-xs text-muted-foreground sm:block">
            {allGear.length} items · {lockers.length} lockers
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:px-6 space-y-6">
        <GearItemManager lockers={lockers} />
        <GearItemList data={allGear} />
      </main>

      <footer className="border-t">
        <div className="mx-auto max-w-3xl px-4 py-4 text-xs text-muted-foreground sm:px-6">
          GearHut — SESSION040 demonstration. Generated with the frozen
          Qwen2.5-Coder-0.5B under contract-first prompts; per-file attribution
          in the research repository.
        </div>
      </footer>
    </div>
  )
}
