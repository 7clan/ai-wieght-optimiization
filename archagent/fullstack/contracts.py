"""Track D — staged exact-shape contracts for StockPilot (Session 035).

Session-034 discipline: the harness names the interface (file, exports,
props, imports, frozen strings); the model writes every byte of the
implementation and chooses conforming values.  Demos are from the pet
shelter domain — never the target names.  Each contract carries its
own gates; acceptance is automatic.
"""
from __future__ import annotations

# ---------------------------------------------------------------- helpers

SCHEMA_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a Prisma model block.  That task was "store
adoption records", and the correct answer was:

model Adoption {
  id         String   @id @default(cuid())
  name       String
  species    String
  age        Int
  updatedAt  DateTime @updatedAt
}"""

TYPE_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a shared types file.  That task defined the
adoption domain types, and the correct answer was:

export interface AdoptionRecord {
  id: string
  name: string
  species: string
  age: number
  updatedAt: string
}

export interface AdoptionInput {
  name: string
  species: string
  age: number
}

export type CareLevel = 'easy' | 'moderate' | 'intensive'

export function careLevelOf(age: number, sickDays: number): CareLevel {
  if (sickDays > 3) return 'intensive'
  if (sickDays > 0) return 'moderate'
  return 'easy'
}"""

CLIENT_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for an API client module.  That task wrapped the
adoptions REST API, and the correct answer was:

async function getJson(res: Response) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(body.error || 'request failed')
  }
  return res.json()
}

export async function listAdoptions(q: string): Promise<AdoptionRecord[]> {
  const params = q ? `?q=${encodeURIComponent(q)}` : ''
  const data = await getJson(await fetch(`/api/adoptions${params}`))
  return data.items
}

export async function createAdoption(input: AdoptionInput): Promise<AdoptionRecord> {
  const data = await getJson(await fetch('/api/adoptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))
  return data.item
}"""

ROUTE_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a list+create route.  That task was "list and
create adoption records", and the correct answer was:

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q')?.trim().toLowerCase() ?? ''
  const rows = await db.adoption.findMany({
    where: q ? { OR: [{ name: { contains: q } }, { species: { contains: q } }] } : {},
    orderBy: { updatedAt: 'desc' },
  })
  const items = rows.map((r) => ({ ...r, updatedAt: r.updatedAt.toISOString() }))
  return NextResponse.json({ items, total: items.length })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const name = String(body.name ?? '').trim()
  const species = String(body.species ?? '').trim()
  const age = Number(body.age)
  if (name.length < 1 || name.length > 60) {
    return NextResponse.json({ error: 'name is required (1-60 chars)' }, { status: 400 })
  }
  if (species.length < 1 || species.length > 40) {
    return NextResponse.json({ error: 'species is required (1-40 chars)' }, { status: 400 })
  }
  if (!Number.isInteger(age) || age < 0 || age > 40) {
    return NextResponse.json({ error: 'age must be an integer 0-40' }, { status: 400 })
  }
  const row = await db.adoption.create({ data: { name, species, age } })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } }, { status: 201 })
}"""

IDROUTE_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a one-record route (get/update/delete by id).
The pet-shelter answer was:

import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

type Params = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params
  const row = await db.adoption.findUnique({ where: { id } })
  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } })
}

export async function PUT(req: NextRequest, { params }: Params) {
  const { id } = await params
  const body = await req.json()
  const age = Number(body.age)
  if (!Number.isInteger(age) || age < 0 || age > 40) {
    return NextResponse.json({ error: 'age must be an integer 0-40' }, { status: 400 })
  }
  const row = await db.adoption.update({
    where: { id },
    data: { name: String(body.name ?? '').trim(), age },
  }).catch(() => null)
  if (!row) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return NextResponse.json({ item: { ...row, updatedAt: row.updatedAt.toISOString() } })
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id } = await params
  const ok = await db.adoption.delete({ where: { id } }).then(() => true).catch(() => false)
  if (!ok) return NextResponse.json({ error: 'not found' }, { status: 404 })
  return new NextResponse(null, { status: 204 })
}"""

HOOK_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a data-fetching hook.  That task was "load
adoptions with loading + error + retry", and the correct answer was:

'use client'

import { useCallback, useEffect, useState } from 'react'
import { listAdoptions, AdoptionRecord } from '@/lib/shelter/client'

export function useAdoptions() {
  const [items, setItems] = useState<AdoptionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await listAdoptions(''))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return { items, loading, error, reload: load }
}"""

COMPONENT_DEMO = """Example from a DIFFERENT app (a pet shelter),
showing the ANSWER FORMAT for a presentational component.  That task
was "a stats strip for the shelter dashboard", and the correct answer
was:

'use client'

import { Card, CardContent } from '@/components/ui/card'

export function ShelterStats({ total, sick }: { total: number; sick: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{total}</div>
          <div className="text-xs text-muted-foreground">Animals</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{sick}</div>
          <div className="text-xs text-muted-foreground">Sick now</div>
        </CardContent>
      </Card>
    </div>
  )
}"""

FORM_DEMO = """Example from a DIFFERENT app (a pet shelter), showing
the ANSWER FORMAT for a dialog form component.  That task was "create
or edit an adoption record", and the correct answer was:

'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type Initial = { id?: string; name: string; age: number }

export function AdoptionForm({ open, initial, onClose, onSaved }:
  { open: boolean; initial: Initial | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('')
  const [age, setAge] = useState('0')
  const [errors, setErrors] = useState<{ name?: string; age?: string }>({})

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? '')
      setAge(String(initial?.age ?? 0))
      setErrors({})
    }
  }, [open, initial])

  function submit() {
    const errs: typeof errors = {}
    const trimmed = name.trim()
    if (trimmed.length < 1 || trimmed.length > 60) errs.name = 'name is required (1-60 chars)'
    const n = Number(age)
    if (!Number.isInteger(n) || n < 0 || n > 40) errs.age = 'age must be an integer 0-40'
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    onSaved()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{initial?.id ? 'Edit record' : 'New record'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="pet-name">Name</Label>
            <Input id="pet-name" value={name} onChange={(e) => setName(e.target.value)} />
            {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}"""

# ---------------------------------------------------------------- contracts

CONTRACTS = [
    dict(
        id="schema", file="prisma/schema.prisma", kind="schema",
        demo=SCHEMA_DEMO,
        spec="""Write the Prisma model block for InventoryItem with
exactly these fields and rules:
- id: String, primary key, @default(cuid())
- name: String
- category: String
- sku: String, optional (nullable)
- quantity: Int
- minQuantity: Int
- updatedAt: DateTime with @updatedAt
Write the model block only (the datasource is already configured).""",
        anchor="model InventoryItem {\n",
        gates=["prisma"],
        max_tokens=300,
    ),
    dict(
        id="types", file="src/lib/inventory/types.ts", kind="file",
        demo=TYPE_DEMO,
        spec="""Write the shared inventory types file with exactly these
exports:
1. export interface InventoryItem — fields: id, name, category,
   sku (string | null), quantity, minQuantity (number), updatedAt
   (string).
2. export interface InventoryInput — fields: name, category,
   sku (string, may be empty string), quantity, minQuantity (number).
3. export type StockStatus = 'in stock' | 'low stock' | 'out of stock'
4. export function stockStatus(quantity: number, minQuantity: number):
   StockStatus — returns 'out of stock' when quantity is 0,
   'low stock' when quantity <= minQuantity (and > 0), else 'in stock'.""",
        anchor="export interface InventoryItem {\n",
        gates=["tsc", "eslint", "types_unit"],
        max_tokens=550,
        exports=['InventoryItem', 'InventoryInput', 'StockStatus', 'stockStatus'],
    ),
    dict(
        id="client", file="src/lib/inventory/api-client.ts", kind="file",
        demo=CLIENT_DEMO,
        spec="""Write the API client for /api/items with exactly these
exports (all fetch the same origin, relative URLs):
1. async function listItems(params): params is an object with optional
   q, category, status, sort, order (all strings). Build a query
   string from the defined, non-empty values (skip 'all' / empty).
   GET /api/items?<params> and return the parsed JSON (has .items).
2. async function createItem(input: InventoryInput): POST JSON to
   /api/items, return parsed .item.
3. async function updateItem(id: string, input: InventoryInput): PUT
   JSON to /api/items/:id, return parsed .item.
4. async function deleteItem(id: string): DELETE /api/items/:id, do
   not parse a body (204).
All functions must throw an Error with the server's .error message
when the response is not ok. Include one small non-exported helper
getJson(res) that does the ok-check and parsing.""",
        anchor="async function getJson(res: Response) {\n",
        gates=["tsc", "eslint"],
        max_tokens=700,
        exports=['listItems', 'createItem', 'updateItem', 'deleteItem'],
    ),
    dict(
        id="route-list", file="src/app/api/items/route.ts", kind="file",
        demo=ROUTE_DEMO,
        spec="""Write the list+create route for inventory items.
GET /api/items:
- read query params q, category, status, sort, order
- q: case-insensitive contains match on name OR sku (use Prisma OR +
  contains with mode: 'insensitive')
- category: exact match unless it is empty or 'all'
- status: 'low' -> quantity > 0 AND quantity <= minQuantity; 'out' ->
  quantity = 0; 'ok' -> quantity > minQuantity; 'all'/empty -> no
  filter (build the Prisma where object only from defined filters)
- sort: 'name' | 'quantity' | 'updatedAt' (default 'updatedAt'),
  order 'asc' | 'desc' (default 'desc'); map to a Prisma orderBy object
- respond 200 with { items, total } where items have updatedAt as
  ISO string (map rows like the demo)
POST /api/items:
- validate with the EXACT frozen rules: name trim 1-80 chars,
  category trim 1-40 chars, sku optional trim <= 40 (empty string ->
  null), quantity integer 0-1000000, minQuantity integer 0-100000
- any invalid field -> 400 { error: '<message>' }
- create via db.inventoryItem.create, respond 201 { item } (updatedAt
  as ISO string)""",
        anchor="import { NextRequest, NextResponse } from 'next/server'\n",
        gates=["tsc", "eslint"],
        max_tokens=900,
        exports=['GET', 'POST'],
    ),
    dict(
        id="route-id", file="src/app/api/items/[id]/route.ts", kind="file",
        demo=IDROUTE_DEMO,
        spec="""Write the one-item route (by id) for inventory items,
Next.js 16 App Router style: params is a Promise you must await
(see the demo).
GET /api/items/:id -> 200 { item } or 404 { error: 'not found' }
PUT /api/items/:id -> validate the body with the SAME frozen rules as
POST (name 1-80, category 1-40, sku <= 40 or null, quantity integer
0-1000000, minQuantity integer 0-100000); invalid -> 400 { error };
unknown id -> 404; success -> 200 { item } (updatedAt ISO string)
DELETE /api/items/:id -> 204 empty body on success, 404 { error }
when the id does not exist (catch the Prisma error like the demo).""",
        anchor="import { NextRequest, NextResponse } from 'next/server'\n",
        gates=["tsc", "eslint", "apitest"],
        max_tokens=900,
        exports=['GET', 'PUT', 'DELETE'],
    ),
    dict(
        id="states", file="src/components/stockpilot/states.tsx", kind="file",
        demo=COMPONENT_DEMO,
        spec="""Write the three state components (one file, all
'use client'):
1. export function EmptyState({ onAdd }: { onAdd: () => void }) —
   shown when there are NO items at all. Contains a heading with the
   exact text 'No items yet', one short sentence inviting the user to
   add the first item, and a Button (accessible name 'Add Item') that
   calls onAdd.
2. export function NoMatchesState({ onClear }: { onClear: () => void })
   — shown when filters/search match nothing. Contains the exact text
   'No items match' plus a short hint, and a Button with accessible
   name containing 'Clear' that calls onClear.
3. export function ErrorState({ message, onRetry }:
   { message: string; onRetry: () => void }) — shown when the API
   failed. Shows the message, the word 'error' (e.g. in the title),
   and a Button with accessible name 'Retry' that calls onRetry.
Use Card from '@/components/ui/card' and Button from
'@/components/ui/button'. Center the content with padding.""",
        anchor="'use client'\n",
        gates=["tsc", "eslint"],
        max_tokens=700,
        exports=['EmptyState', 'NoMatchesState', 'ErrorState'],
    ),
    dict(
        id="stats", file="src/components/stockpilot/stats-bar.tsx", kind="file",
        demo=COMPONENT_DEMO,
        spec="""Write the stats strip component:
export function StatsBar({ items }: { items: InventoryItem[] }) —
computes from the given array: total items, total units (sum of
quantity), low stock count (0 < quantity <= minQuantity), out of stock
count (quantity = 0). Renders four Cards in a responsive grid
(grid-cols-2 on mobile, sm:grid-cols-4) like the demo. Labels exactly:
'Total items', 'Total units', 'Low stock', 'Out of stock'. Numbers
tabular-nums. Import InventoryItem from '@/lib/inventory/types'.""",
        anchor="'use client'\n\nimport { Card, CardContent } from '@/components/ui/card'\n",
        gates=["tsc", "eslint"],
        max_tokens=450,
        exports=['StatsBar'],
    ),
    dict(
        id="toolbar", file="src/components/stockpilot/toolbar.tsx", kind="file",
        demo=COMPONENT_DEMO,
        spec="""Write the toolbar component:
export function Toolbar({ q, category, status, sort, order,
categories, onChange }: { q: string; category: string; status: string;
sort: string; order: string; categories: string[]; onChange: (patch:
Partial<{ q: string; category: string; status: string; sort: string;
order: string }>) => void })
Renders in a responsive flex column on mobile / row on desktop:
1. an Input with placeholder 'Search items…' bound to q
2. a Select for 'Category' with options: 'All categories' (value
   'all'), then one option per category string
3. a Select for 'Status' with options 'All statuses'/'In stock'/
   'Low stock'/'Out of stock' (values 'all'/'ok'/'low'/'out')
4. a Select for 'Sort by' with options 'Updated'/'Name'/'Quantity'
   (values 'updatedAt'/'name'/'quantity')
5. a Select for 'Order' with options 'Descending'/'Ascending'
   (values 'desc'/'asc')
Each Select calls onChange with its patch, e.g.
onChange({ category: value }). Use Select, SelectTrigger, SelectValue,
SelectContent, SelectItem from '@/components/ui/select' and Input from
'@/components/ui/input'. Wrap selects in a div with class
'flex flex-wrap items-center gap-2'.""",
        anchor="'use client'\n\nimport { Input } from '@/components/ui/input'\n",
        gates=["tsc", "eslint"],
        max_tokens=800,
        exports=['Toolbar'],
    ),
    dict(
        id="table", file="src/components/stockpilot/item-table.tsx", kind="file",
        demo=COMPONENT_DEMO,
        spec="""Write the item list component:
export function ItemTable({ items, onEdit, onDelete }:
{ items: InventoryItem[]; onEdit: (item: InventoryItem) => void;
onDelete: (item: InventoryItem) => void })
Desktop (hidden on small screens: className 'hidden md:block'):
a Table with header columns Name, SKU, Category, Quantity, Status,
Updated, Actions; body rows per item showing the fields, a status
Badge per the frozen rule ('In stock' default variant, 'Low stock'
with a warning look (className 'border-amber-500/50 text-amber-700'
plus variant 'outline'), 'Out of stock' variant 'destructive'), and
Actions = two small Buttons accessible-named 'Edit' and 'Delete'
(variant 'ghost', size 'icon', with title/aria-label 'Edit'/'Delete')
calling onEdit/onDelete with the row's item. Updated shows a short
date (new Date(updatedAt).toLocaleDateString()).
Mobile (md:hidden): stacked Cards (one per item) showing name, sku,
category, quantity, the same Badge, and the same Edit/Delete buttons
(all information must be present).
Use Table, TableBody, TableCell, TableHead, TableHeader, TableRow from
'@/components/ui/table', Badge from '@/components/ui/badge', Button
from '@/components/ui/button', Card/CardContent from
'@/components/ui/card'. Import stockStatus and InventoryItem from
'@/lib/inventory/types'.""",
        anchor="'use client'\n\nimport { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'\n",
        gates=["tsc", "eslint"],
        max_tokens=1000,
        exports=['ItemTable'],
    ),
    dict(
        id="form", file="src/components/stockpilot/item-form.tsx", kind="file",
        demo=FORM_DEMO,
        spec="""Write the create/edit item form dialog:
export function ItemForm({ open, initial, onClose, onSaved }:
{ open: boolean; initial: InventoryItem | null; onClose: () => void;
onSaved: (input: InventoryInput) => void })
- local state for name, category, sku, quantity, minQuantity as
  strings; when the dialog opens, initialize from initial (edit mode)
  or defaults: name '', category '', sku '', quantity '0',
  minQuantity '5'
- fields with Labels exactly 'Name', 'Category', 'SKU', 'Quantity',
  'Min quantity' (Label htmlFor matches Input id)
- inline validation errors under each field, same frozen rules as the
  API (name 1-80, category 1-40, sku <= 40, quantity integer
  0-1000000, minQuantity integer 0-100000)
- Save button (accessible name 'Save') submits: validate; if ok call
  onSaved({ name, category, sku, quantity, minQuantity }) with numbers
  parsed; if invalid, show the errors and keep the dialog open
- Cancel button and dialog X call onClose
- DialogTitle: 'Add item' when initial is null, 'Edit item' otherwise
Use Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle
from '@/components/ui/dialog', Button, Input, Label like the demo.
Import InventoryItem, InventoryInput from '@/lib/inventory/types'.""",
        anchor="'use client'\n\nimport { useEffect, useState } from 'react'\n",
        gates=["tsc", "eslint"],
        max_tokens=1000,
        exports=['ItemForm'],
    ),
    dict(
        id="hook", file="src/lib/inventory/use-inventory.ts", kind="file",
        demo=HOOK_DEMO,
        spec="""Write the inventory data hook:
export function useInventory() — client hook returning
{ items, loading, error, reload, patch, q, category, status, sort,
order } where:
- state: items (InventoryItem[]), loading (bool, starts true), error
  (string | null), and filter state q/category/status/sort/order with
  defaults '', 'all', 'all', 'updatedAt', 'desc'
- patch(partial) merges into the filter state
- an effect depends on [q, category, status, sort, order] and calls
  listItems with the current filters (debounced ~300ms for q:
  simplest correct form — setTimeout cleared on cleanup, always
  applied); sets loading true before, false after; on throw sets
  error to the message
- reload() forces a refetch (a counter state in the effect deps)
- the categories list is NOT this hook's job
Import listItems and the types from '@/lib/inventory/types' and
'@/lib/inventory/api-client'. The file starts with 'use client'.""",
        anchor="'use client'\n\nimport { useCallback, useEffect, useState } from 'react'\n",
        gates=["tsc", "eslint"],
        max_tokens=700,
        exports=['useInventory'],
    ),
    dict(
        id="page", file="src/app/page.tsx", kind="file",
        demo=COMPONENT_DEMO,
        spec="""Write the StockPilot page assembling every piece:
'use client' page component that:
1. uses useInventory() from '@/lib/inventory/use-inventory'
2. local state: formOpen (bool), editing (InventoryItem | null),
   confirmItem (InventoryItem | null), toast (string | null, cleared
   by setTimeout 3s)
3. derives categories: [...new Set(items.map(i => i.category))].sort()
4. renders, in order:
   - a header: an h1 with 'StockPilot', a p subtitle 'Track stock
     levels, categories and low-stock alerts', and a Button 'Add
     Item' (opens the form with editing=null)
   - StatsBar with the current items
   - Toolbar with the filter state and patch
   - the main section: when error -> ErrorState (message + onRetry
     reload); when loading -> a loading element with role='status'
     and visible text 'Loading items…' (may use Skeleton cards);
     when items.length === 0 && no active filters (q=='' and
     category=='all' and status=='all') -> EmptyState (onAdd opens
     the form); when items.length === 0 -> NoMatchesState (onClear
     resets filters via patch); otherwise ItemTable
   - ItemForm (open, initial=editing, onClose, onSaved: calls
     createItem or updateItem depending on editing, closes the form,
     sets toast 'Item added'/'Item updated', calls reload; on client
     error sets toast to the message)
   - a delete confirm Dialog when confirmItem is set: text mentions
     deleting the item by name; buttons 'Cancel' and a destructive
     'Delete' that calls deleteItem(confirmItem.id), closes, sets
     toast 'Item deleted', reloads
   - the toast: a div with role='status' showing the toast text
     (fixed bottom-right, simple styling)
5. onSaved also needs the created input assembled from the form —
   ItemForm passes the InventoryInput directly to onSaved.
Imports: Button from '@/components/ui/button', Dialog pieces from
'@/components/ui/dialog', all stockpilot components, the client
functions, and the types.""",
        anchor="'use client'\n\nimport { useState } from 'react'\n",
        gates=["tsc", "eslint", "uitest"],
        max_tokens=1300,
        exports=['default'],
    ),
]
