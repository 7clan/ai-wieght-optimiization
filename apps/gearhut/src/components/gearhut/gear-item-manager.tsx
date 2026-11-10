'use client';

// SESSION040 GearHut — attribution: QWEN_GENERATED core with disclosed fixes.
// The state machine, fetch flow, create form and refresh behavior are the
// frozen model's generation (app/evidence/gearhut__fullstack-integration.json,
// attempt 1, zero repairs). Teacher changes, all marked [TEACHER]:
//   1. bug fix: the model called setError() without declaring the state
//   2. bug fix: `gear` initialized to null crashed .map before first load
//   3. bug fix: usageHours input max was 100 (contract: 2000); state kept as
//      string so the form preserves typing
//   4. feature: server-side search/status filters that refetch with query
//      params (makes the GET route contract load-bearing in the UI)
//   5. feature: per-row advance/delete actions (PATCH/DELETE via the
//      QWEN-REPAIRED invariant)
//   6. presentation: raw HTML elements swapped for shadcn/ui equivalents
// Original bytes archived in app/generated/gear-item-manager.tsx.

import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'

const ROUTE = '/api/gearhut-items'

type GearItem = {
  id: string; label: string; usageHours: number;
  status: string; lockerId: string;
}

const STATUS_BADGE: Record<string, string> = {
  stashed: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  inspected: 'bg-amber-100 text-amber-900 border-amber-300',
  retired: 'bg-zinc-200 text-zinc-700 border-zinc-400',
}

export default function GearItemManager({ lockers }: { lockers: { id: string; name: string | null }[] }) {
  const [gear, setGear] = useState<GearItem[]>([])          // [TEACHER] was null (bug 2)
  const [total, setTotal] = useState(0)
  const [label, setLabel] = useState('')
  const [usageHours, setUsageHours] = useState('0')          // [TEACHER] string state (bug 3)
  const [lockerId, setLockerId] = useState(lockers[0]?.id ?? '')
  const [error, setError] = useState('')                     // [TEACHER] missing state (bug 1)
  const [search, setSearch] = useState('')                   // [TEACHER] feature 4
  const [status, setStatus] = useState('all')                // [TEACHER] feature 4
  const [busy, setBusy] = useState(false)                    // [TEACHER] feature 5

  const load = useCallback(async (opts?: { search?: string; status?: string }) => {
    const s = opts?.search ?? search
    const st = opts?.status ?? status
    const query = new URLSearchParams()
    if (s) query.set('search', s)
    if (st && st !== 'all') query.set('status', st)
    const response = await fetch(`${ROUTE}${query.size ? `?${query}` : ''}`)
    const data = await response.json()
    setGear(data.gear || [])
    setTotal(data.total ?? 0)
  }, [search, status])

  useEffect(() => { load() }, [])

  // [TEACHER] feature 4: refetch when filters change (server-side filtering)
  useEffect(() => {
    const timer = setTimeout(() => { load() }, 200)
    return () => clearTimeout(timer)
  }, [search, status, load])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    const response = await fetch(ROUTE, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ label, usageHours: Number(usageHours), lockerId }),
    })
    if (response.status === 201) {
      setLabel('')
      await load()
    } else {
      const data = await response.json().catch(() => ({}))
      setError(data.error || `Request failed (${response.status})`)
    }
  }

  // [TEACHER] feature 5: advance / delete row actions
  const advance = async (item: GearItem) => {
    setBusy(true); setError('')
    try {
      const order = ['stashed', 'inspected', 'retired']
      const next = order[order.indexOf(item.status) + 1]
      if (!next) return
      const response = await fetch(`${ROUTE}/${item.id}`, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ status: next }),
      })
      if (response.ok) { await load() }
      else {
        const data = await response.json().catch(() => ({}))
        setError(data.error || `Request failed (${response.status})`)
      }
    } finally { setBusy(false) }
  }

  const remove = async (item: GearItem) => {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${ROUTE}/${item.id}`, { method: 'DELETE' })
      if (response.ok) { await load() }
      else {
        const data = await response.json().catch(() => ({}))
        setError(data.error || `Request failed (${response.status})`)
      }
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add gear</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
            <div className="grid gap-2">
              <Label htmlFor="label">Label</Label>
              <Input id="label" value={label} placeholder="e.g. Canyon rope 60m"
                     onChange={(event) => setLabel(event.target.value)} required />
            </div>
            <div className="grid gap-2 w-full sm:w-32">
              <Label htmlFor="usageHours">Usage hours</Label>
              <Input id="usageHours" type="number" min={0} max={2000} value={usageHours}
                     onChange={(event) => setUsageHours(event.target.value)} />
            </div>
            <div className="grid gap-2 w-full sm:w-48">
              <Label htmlFor="lockerId">Locker</Label>
              <Select value={lockerId} onValueChange={setLockerId}>
                <SelectTrigger id="lockerId"><SelectValue placeholder="Locker" /></SelectTrigger>
                <SelectContent>
                  {lockers.map((locker) => (
                    <SelectItem key={locker.id} value={locker.id}>
                      {locker.name || 'Unnamed locker'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={busy}>Create</Button>
          </form>
          {error ? (
            <p role="alert" className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Gear ({total})</CardTitle>
          <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
            <div className="grid gap-1.5">
              <Label htmlFor="gear-search" className="sr-only">Search gear</Label>
              <Input id="gear-search" type="search" value={search} placeholder="Search gear…"
                     className="sm:w-56" onChange={(event) => setSearch(event.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="gear-status" className="sr-only">Filter by status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="gear-status" className="sm:w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="stashed">Stashed</SelectItem>
                  <SelectItem value="inspected">Inspected</SelectItem>
                  <SelectItem value="retired">Retired</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {gear.length === 0 ? (
            <p data-testid="empty-state" className="rounded-md border border-dashed px-4 py-8 text-center text-muted-foreground">
              No gear matches your filters.
            </p>
          ) : (
            <ul className="divide-y">
              {gear.map((gearItem) => (
                <li key={gearItem.id}
                    className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{gearItem.label}</p>
                    <p className="text-sm text-muted-foreground">
                      {gearItem.usageHours} usage hours
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className={STATUS_BADGE[gearItem.status] ?? ''}>
                      {gearItem.status}
                    </Badge>
                    {gearItem.status !== 'retired' ? (
                      <Button size="sm" variant="outline" disabled={busy}
                              onClick={() => advance(gearItem)}>
                        Advance
                      </Button>
                    ) : null}
                    <Button size="sm" variant="ghost" disabled={busy}
                            className="text-destructive hover:text-destructive"
                            onClick={() => remove(gearItem)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
