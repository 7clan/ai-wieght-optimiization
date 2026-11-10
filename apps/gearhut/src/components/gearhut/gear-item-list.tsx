'use client';

// SESSION040 GearHut — attribution: QWEN_GENERATED core, TEACHER-CORRECTED
// vocabulary. The component structure (search state, status state, combined
// client-side filter, clear button, explicit empty state) is the frozen
// model's generation (app/evidence/gearhut__react-interaction.json, attempt
// 1, zero repairs). Teacher corrections, all vocabulary-level (the model
// copied the greenhouse demo's words — the documented failure mode):
//   - labels/ids: sensor-search/sensor-status -> gear-quick-search/gear-quick-status
//   - status options: calibrating/monitoring -> stashed/inspected
//   - row field: row.reading -> row.usageHours
//   - empty-state text: "No sensors match" -> "No gear matches"
//   - presentation: shadcn equivalents for the raw elements
// Original bytes archived in app/generated/gear-item-list.tsx.

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

type Row = { id: string; label: string; usageHours: number; status: string }

export default function GearItemList({ data }: { data: Row[] }) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const rows = (data || []).filter((row) =>
    (!search || row.label.toLowerCase().includes(search.toLowerCase()))
    && (status === 'all' || row.status === status))
  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle>Quick filter <span className="text-sm font-normal text-muted-foreground">(client-side)</span></CardTitle>
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-center">
          <div className="grid gap-1.5">
            <Label htmlFor="gear-quick-search" className="sr-only">Search gear</Label>
            <Input id="gear-quick-search" type="search" value={search} placeholder="Search gear…"
                   className="sm:w-52" onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="gear-quick-status" className="sr-only">Filter by status</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger id="gear-quick-status" className="sm:w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="stashed">Stashed</SelectItem>
                <SelectItem value="inspected">Inspected</SelectItem>
                <SelectItem value="retired">Retired</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button type="button" variant="outline"
                  onClick={() => { setSearch(''); setStatus('all'); }}>
            Clear filters
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p data-testid="empty-state" className="rounded-md border border-dashed px-4 py-6 text-center text-muted-foreground">
            No gear matches your filters.
          </p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {rows.map((row) => (
              <li key={row.id}
                  className="rounded-md border px-3 py-2 text-sm flex items-center justify-between gap-2">
                <span className="truncate font-medium">{row.label}</span>
                <span className="whitespace-nowrap text-muted-foreground">
                  {row.usageHours}h · {row.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
