"""UI stage, round 2 — calibrated per-component contracts (Session 035).

Whole-file UI contracts (trackD17) failed on a systematic demo-label
trap: the model copies the demo's visible labels ('Animals', 'Sick
now') verbatim, which the demo-echo blacklist then rejects (11/12
states samples; same pattern expected for every UI file sharing
COMPONENT_DEMO).  Diagnosis: demos must show STRUCTURE with neutral
labels; the frozen strings come from the spec's explicit text.

This runner generates every remaining UI file from per-component
contracts (states split into three single-component contracts), each
with: concept + neutral-label demo + explicit spec (frozen strings) +
anchor + strict expects (the frozen strings themselves).  Acceptance
is automatic; failures are recorded for the teacher decision.
"""
from __future__ import annotations

import gc
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.fullstack import runner_d  # noqa: E402
from archagent.fullstack.contracts import CONTRACTS  # noqa: E402
from archagent.fullstack.gen_one import strip_prompt_echo, DEMO_ECHO  # noqa: E402
from archagent.fullstack.route_round2 import cut_repetition, _balance  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402

EXP = ROOT / "experiments/zai-fullstack"
GEN = EXP / "generations"
LEDGER = EXP / "PROVENANCE.json"
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/.npm-global/lib/node_modules",
    BASE="http://127.0.0.1:3000",
)


def log(msg: str) -> None:
    print(msg, flush=True)


CONCEPT = """You write React client components in TypeScript for
Next.js.  The imports are already written.  Write plain TSX: no
comments, no TODOs, correct JSX for every element."""

NEUTRAL_CARD_DEMO = """Example from a DIFFERENT app, showing the ANSWER
FORMAT for a small presentational component (labels here are
placeholders — always use the strings YOUR task asks for):

'use client'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function DemoPanel({ count, onAction }: { count: number; onAction: () => void }) {
  return (
    <Card>
      <CardContent className="p-6 text-center">
        <div className="text-2xl font-semibold tabular-nums">{count}</div>
        <div className="text-xs text-muted-foreground">Label text</div>
        <Button onClick={onAction}>Action</Button>
      </CardContent>
    </Card>
  )
}"""

NEUTRAL_FORM_DEMO = """Example from a DIFFERENT app, showing the ANSWER
FORMAT for a dialog form component (labels and rules here are
placeholders — always use the strings and rules YOUR task asks for):

'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type Initial = { id?: string; title: string; size: number }

export function DemoForm({ open, initial, onClose, onSaved }:
  { open: boolean; initial: Initial | null; onClose: () => void; onSaved: (input: Initial) => void }) {
  const [title, setTitle] = useState('')
  const [size, setSize] = useState('0')
  const [errors, setErrors] = useState<{ title?: string; size?: string }>({})

  useEffect(() => {
    if (open) {
      setTitle(initial?.title ?? '')
      setSize(String(initial?.size ?? 0))
      setErrors({})
    }
  }, [open, initial])

  function submit() {
    const errs: typeof errors = {}
    const trimmed = title.trim()
    if (trimmed.length < 1 || trimmed.length > 60) errs.title = 'title is required (1-60 chars)'
    const n = Number(size)
    if (!Number.isInteger(n) || n < 0 || n > 500) errs.size = 'size must be an integer 0-500'
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    onSaved({ title: trimmed, size: n })
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{initial?.id ? 'Edit entry' : 'New entry'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="demo-title">Title</Label>
            <Input id="demo-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            {errors.title && <p className="text-xs text-destructive">{errors.title}</p>}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="demo-size">Size</Label>
            <Input id="demo-size" value={size} onChange={(e) => setSize(e.target.value)} />
            {errors.size && <p className="text-xs text-destructive">{errors.size}</p>}
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

HOOK_DEMO = """Example from a DIFFERENT app, showing the ANSWER FORMAT
for a data hook with an inline fetch layer (names here are
placeholders — always use the names YOUR task asks for):

'use client'

import { useCallback, useEffect, useState } from 'react'

type Row = { id: string; title: string; size: number }

async function getJson(res: Response) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'request failed' }))
    throw new Error(body.error)
  }
  return res.json()
}

export function useRows() {
  const [items, setItems] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getJson(await fetch('/api/rows'))
      setItems(data.items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function saveRow(input: Row, id?: string) {
    const res = await fetch(id ? `/api/rows/${id}` : '/api/rows', {
      method: id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
    await getJson(res)
    await load()
  }

  return { items, loading, error, reload: load, saveRow }
}"""

TABLE_DEMO = """Example from a DIFFERENT app, showing the ANSWER FORMAT
for a list component with a desktop table and mobile cards (labels
here are placeholders — always use the strings YOUR task asks for):

'use client'

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

export function DemoTable({ rows, onEdit, onDelete }:
  { rows: { id: string; title: string; size: number }[]; onEdit: (r: any) => void; onDelete: (r: any) => void }) {
  return (
    <div>
      <div className="hidden md:block rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Size</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="font-medium">{r.title}</TableCell>
                <TableCell className="tabular-nums">{r.size}</TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" title="Edit" aria-label="Edit" onClick={() => onEdit(r)}>E</Button>
                  <Button variant="ghost" size="icon" title="Delete" aria-label="Delete" onClick={() => onDelete(r)}>D</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="md:hidden grid gap-3">
        {rows.map((r) => (
          <Card key={r.id}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{r.title}</div>
                <Badge variant="outline">size {r.size}</Badge>
              </div>
              <div className="mt-2 flex gap-2">
                <Button variant="outline" size="sm" onClick={() => onEdit(r)}>Edit</Button>
                <Button variant="outline" size="sm" onClick={() => onDelete(r)}>Delete</Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}"""

# ------------------------------------------------------------------ contracts

UI_CONTRACTS = [
    dict(
        cid="ui-empty", file="src/components/stockpilot/states.tsx",
        part="EmptyState", demo=NEUTRAL_CARD_DEMO, tok=420,
        anchor="'use client'\n\nimport { Button } from '@/components/ui/button'\n",
        spec="""Write the EmptyState component (one exported function
in the file):
export function EmptyState({ onAdd }: { onAdd: () => void }) —
shown when there are NO items at all.  It renders a centered Card
containing: a heading with the exact text 'No items yet', one short
sentence inviting the user to add the first item, and a Button with
the exact text 'Add Item' that calls onAdd.  Center the content
with padding (like the demo).""",
        expects=["export function EmptyState", "No items yet",
                 "Add Item", "onAdd"],
    ),
    dict(
        cid="ui-nomatch", file="src/components/stockpilot/states.tsx",
        part="NoMatchesState", demo=NEUTRAL_CARD_DEMO, tok=420,
        anchor="'use client'\n\nimport { Button } from '@/components/ui/button'\n",
        spec="""Write the NoMatchesState component:
export function NoMatchesState({ onClear }: { onClear: () => void })
— shown when search/filters match nothing.  It renders a centered
Card containing: the exact text 'No items match', a short hint
mentioning the search or filters, and a Button whose accessible name
contains 'Clear' that calls onClear.""",
        expects=["export function NoMatchesState", "No items match",
                 "Clear", "onClear"],
    ),
    dict(
        cid="ui-error", file="src/components/stockpilot/states.tsx",
        part="ErrorState", demo=NEUTRAL_CARD_DEMO, tok=420,
        anchor="'use client'\n\nimport { Button } from '@/components/ui/button'\n",
        spec="""Write the ErrorState component:
export function ErrorState({ message, onRetry }:
{ message: string; onRetry: () => void }) — shown when the API
failed.  It renders a centered Card containing: a heading that
includes the word 'Error', the message text, and a Button with the
exact text 'Retry' that calls onRetry.""",
        expects=["export function ErrorState", "Retry", "message",
                 "onRetry"],
    ),
    dict(
        cid="ui-stats", file="src/components/stockpilot/stats-bar.tsx",
        part="StatsBar", demo=NEUTRAL_CARD_DEMO, tok=450,
        anchor="'use client'\n\nimport { Card, CardContent } from '@/components/ui/card'\n",
        spec="""Write the stats strip component:
export function StatsBar({ items }: { items: InventoryItem[] }) —
computes from the given array: total items (items.length), total
units (sum of quantity), low stock count (items where quantity > 0
and quantity <= minQuantity), out of stock count (quantity === 0).
Renders four Cards in a responsive grid (grid-cols-2 on mobile,
sm:grid-cols-4) exactly like the demo, with the labels exactly:
'Total items', 'Total units', 'Low stock', 'Out of stock' and
tabular-nums numbers.  Import InventoryItem from
'@/lib/inventory/types'.""",
        expects=["export function StatsBar", "Total items",
                 "Total units", "Low stock", "Out of stock",
                 "grid-cols-2", "sm:grid-cols-4"],
    ),
    dict(
        cid="ui-toolbar", file="src/components/stockpilot/toolbar.tsx",
        part="Toolbar", demo=NEUTRAL_CARD_DEMO, tok=800,
        anchor="'use client'\n\nimport { Input } from '@/components/ui/input'\n",
        spec="""Write the toolbar component:
export function Toolbar({ q, category, status, sort, order,
categories, onChange }: { q: string; category: string; status:
string; sort: string; order: string; categories: string[]; onChange:
(patch: Partial<{ q: string; category: string; status: string;
sort: string; order: string }>) => void })
Renders a responsive flex column on mobile / row on desktop
containing:
1. an Input with placeholder 'Search items…' whose value is q and
   onChange calls onChange({ q: e.target.value })
2. a Select for the category: SelectTrigger with SelectValue
   placeholder 'Category'; options: SelectItem value 'all' with text
   'All categories', then one SelectItem per category string (value
   and text both the category)
3. a Select 'Status': options 'All statuses' (value 'all'),
   'In stock' (value 'ok'), 'Low stock' (value 'low'), 'Out of
   stock' (value 'out')
4. a Select 'Sort by': 'Updated' (value 'updatedAt'), 'Name' (value
   'name'), 'Quantity' (value 'quantity')
5. a Select 'Order': 'Descending' (value 'desc'), 'Ascending'
   (value 'asc')
Every Select calls onChange with its patch, e.g.
onChange({ category: value }) on ValueChange.  Use Select,
SelectTrigger, SelectValue, SelectContent, SelectItem from
'@/components/ui/select' and Input from '@/components/ui/input'.
Wrap the selects in a div with className 'flex flex-wrap items-center
gap-2'.""",
        expects=["export function Toolbar", "Search items",
                 "All categories", "All statuses", "In stock",
                 "Low stock", "Out of stock", "Sort by", "Descending",
                 "Ascending", "onChange"],
    ),
    dict(
        cid="ui-table", file="src/components/stockpilot/item-table.tsx",
        part="ItemTable", demo=TABLE_DEMO, tok=1000,
        anchor="'use client'\n\nimport { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'\n",
        spec="""Write the item list component:
export function ItemTable({ items, onEdit, onDelete }:
{ items: InventoryItem[]; onEdit: (item: InventoryItem) => void;
onDelete: (item: InventoryItem) => void })
Desktop table (in a div with className 'hidden md:block rounded-md
border' like the demo): header row with columns Name, SKU, Category,
Quantity, Status, Updated, Actions; one row per item showing the
fields; the Status cell is a Badge: 'In stock' (default variant)
when quantity > minQuantity, 'Low stock' with variant 'outline' and
className 'border-amber-500/50 text-amber-700' when quantity > 0 and
quantity <= minQuantity, 'Out of stock' variant 'destructive' when
quantity is 0; the Actions cell has two icon Buttons with title and
aria-label 'Edit' and 'Delete' calling onEdit(item) / onDelete(item);
the Updated cell shows new Date(item.updatedAt).toLocaleDateString().
Mobile cards (div 'md:hidden grid gap-3' like the demo): one Card
per item showing name, sku, category, quantity, the same Badge, and
Edit/Delete buttons.
Import stockStatus and InventoryItem from '@/lib/inventory/types',
Badge from '@/components/ui/badge', Button from
'@/components/ui/button', Card/CardContent from
'@/components/ui/card'.""",
        expects=["export function ItemTable", "hidden md:block",
                 "md:hidden", "Edit", "Delete", "Name", "Quantity",
                 "stockStatus"],
    ),
    dict(
        cid="ui-form", file="src/components/stockpilot/item-form.tsx",
        part="ItemForm", demo=NEUTRAL_FORM_DEMO, tok=1000,
        anchor="'use client'\n\nimport { useEffect, useState } from 'react'\n",
        spec="""Write the create/edit item form dialog:
export function ItemForm({ open, initial, onClose, onSaved }:
{ open: boolean; initial: InventoryItem | null; onClose: () => void;
onSaved: (input: InventoryInput) => void })
- local state for name, category, sku, quantity, minQuantity as
  strings; when the dialog opens, initialize from initial (edit
  mode) or defaults name '', category '', sku '', quantity '0',
  minQuantity '5' (like the demo's useEffect)
- fields with Labels exactly 'Name', 'Category', 'SKU', 'Quantity',
  'Min quantity'; each Label htmlFor matches its Input id
- inline validation errors under each field with the rules: name
  trimmed 1-80 chars; category trimmed 1-40 chars; sku trimmed at
  most 40 chars; quantity an integer 0-1000000; minQuantity an
  integer 0-100000
- the Save button (exact text 'Save') validates; when valid it calls
  onSaved({ name, category, sku, quantity, minQuantity }) with
  quantity and minQuantity parsed as numbers; when invalid it shows
  the errors and keeps the dialog open
- Cancel button (exact text 'Cancel') and the dialog X call onClose
- DialogTitle is 'Add item' when initial is null, else 'Edit item'
Use Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle
from '@/components/ui/dialog', Button from '@/components/ui/button',
Input from '@/components/ui/input', Label from '@/components/ui/label'.
Import InventoryItem and InventoryInput from
'@/lib/inventory/types'.""",
        expects=["export function ItemForm", "Add item", "Edit item",
                 "'Name'", "'Category'", "'SKU'", "'Quantity'",
                 "'Min quantity'", "Save", "Cancel", "onSaved"],
    ),
    dict(
        cid="ui-hook", file="src/lib/inventory/use-inventory.ts",
        part="useInventory", demo=HOOK_DEMO, tok=1300,
        anchor="'use client'\n\nimport { useCallback, useEffect, useState } from 'react'\n",
        spec="""Write the inventory data hook (all in ONE file, like
the demo):
1. a non-exported helper async function getJson(res: Response) —
   like the demo: if (!res.ok) parse the error body and throw new
   Error(body.error); else return res.json()
2. import { InventoryItem, InventoryInput } from
   '@/lib/inventory/types' and use these EXACT names
3. export function useInventory() returning { items, loading,
   error, reload, patch, q, category, status, sort, order, saveItem,
   removeItem } where:
   - state: items (InventoryItem[]), loading (true initially),
     error (string | null), filter state q/category/status/sort/order
     with defaults '', 'all', 'all', 'updatedAt', 'desc', plus a
     reloadKey number starting at 0
   - patch(partial) merges the partial into the filter state
   - an effect depends on [q, category, status, sort, order,
     reloadKey]; inside, a setTimeout of 300 ms (cleared on cleanup),
     then: setLoading(true); build a URLSearchParams from the
     filters, skipping empty values and 'all' values; fetch the url
     '/api/items?' + params through getJson; setItems(data.items);
     on catch setError(message); finally setLoading(false)
   - reload() increments reloadKey with a state setter
   - async function saveItem(input: InventoryInput, id?: string):
     if id is present, PUT to '/api/items/' + id, else POST to
     '/api/items'; both with headers 'Content-Type': 'application/
     json' and body JSON.stringify({ name: input.name, category:
     input.category, sku: input.sku, quantity: input.quantity,
     minQuantity: input.minQuantity }); through getJson; then call
     reload()
   - async function removeItem(id: string): await fetch(DELETE
     '/api/items/' + id); when res.ok is false throw new Error();
     then reload()""",
        expects=["export function useInventory", "getJson",
                 "reloadKey", "saveItem", "removeItem", "300"],
    ),
    dict(
        cid="ui-page", file="src/app/page.tsx", part="page",
        demo=NEUTRAL_CARD_DEMO, tok=1300,
        anchor="'use client'\n\nimport { useState } from 'react'\n",
        spec="""Write the StockPilot page assembling every piece:
the default-exported page component:
1. calls useInventory() from '@/lib/inventory/use-inventory'
2. local state: formOpen (boolean), editing (InventoryItem | null),
   confirmItem (InventoryItem | null), toast (string | null)
3. derives categories: [...new Set(items.map((i) => i.category))].sort()
4. renders, in order:
   - a header: an h1 with the exact text 'StockPilot', a p with the
     exact subtitle 'Track stock levels, categories and low-stock
     alerts', and a Button 'Add Item' that opens the form with
     editing null
   - StatsBar with the current items
   - Toolbar with the filter state and patch
   - the main section: when error is set, ErrorState with the
     message and onRetry reload; when loading, an element with
     role='status' containing the exact text 'Loading items…'; when
     items.length === 0 and q === '' and category === 'all' and
     status === 'all', EmptyState with onAdd opening the form; when
     items.length === 0, NoMatchesState with onClear resetting the
     filters via patch; otherwise ItemTable
   - ItemForm with open, initial editing, onClose, and onSaved that
     calls saveItem with the form input and editing?.id, closes the
     form, sets toast 'Item added' or 'Item updated'
   - when confirmItem is set, a confirm Dialog: DialogTitle 'Delete
     item', DialogContent with text 'Are you sure you want to delete
     this item?', DialogFooter with a Cancel Button and a
     destructive 'Delete' Button that calls removeItem with
     confirmItem.id, sets confirmItem null and toast 'Item deleted'
   - when toast is set, a div with role='status' and className
     'fixed bottom-4 right-4' showing the toast text
5. Import Button from '@/components/ui/button', Dialog pieces from
'@/components/ui/dialog', EmptyState, NoMatchesState, ErrorState
from '@/components/stockpilot/states', StatsBar from
'@/components/stockpilot/stats-bar', Toolbar from
'@/components/stockpilot/toolbar', ItemTable from
'@/components/stockpilot/item-table', ItemForm from
'@/components/stockpilot/item-form', useInventory from
'@/lib/inventory/use-inventory', InventoryItem from
'@/lib/inventory/types'.""",
        expects=["StockPilot", "Add Item", "StatsBar", "Toolbar",
                 "ItemTable", "ItemForm", "useInventory", "Loading",
                 "role=\"status\""],
    ),
]


def gen_ui(model, c: dict) -> tuple[str | None, dict]:
    """Generate one component file: up to 3 rounds x 4 samples with
    failure feedback; strict frozen-string expects; archive all."""
    feedback = None
    own_prev = None
    for round_no in range(3):
        parts = [CONCEPT, "", c["demo"], "",
                 f"Now YOUR task.  {c['spec']}"]
        if own_prev:
            parts += ["", "Your previous attempt (which failed the "
                           "checks) was:", own_prev[-1000:]]
        if feedback:
            parts += ["", "The automated checks reported:", feedback[-700:],
                      "Fix exactly that."]
        parts += ["", "Write the complete file now.  The first line is "
                      "already written; continue from it:", c["anchor"]]
        prompt = "\n".join(parts)
        for k in range(4):
            seed = (k * 1013 + round_no * 77) or 7
            stochastic = k != 0
            text, usage = model.generate(prompt, max_tokens=c["tok"],
                                         seed=seed, stochastic=stochastic)
            comp = strip_prompt_echo(text.strip("\n"), prompt)
            comp = cut_repetition(comp)
            body = c["anchor"].rstrip("\n") + "\n" + comp
            reasons = []
            for w in DEMO_ECHO:
                if w in comp:
                    reasons.append(f"demo echo {w!r}")
            for need in c["expects"]:
                if need not in body:
                    reasons.append(f"missing {need!r}")
            if "```" in body:
                reasons.append("fence")
            if reasons == [] and not _balance(body):
                reasons.append("brace imbalance")
            ok = not reasons
            (GEN / f"{c['cid']}_r{round_no}_k{k}.json").write_text(
                json.dumps(dict(kind="ui-body", contract=c["cid"],
                                file=c["file"], part=c["part"],
                                round=round_no, k=k, seed=seed,
                                usage=usage, prompt=prompt,
                                completion=text, processed=body,
                                reject=reasons or None),
                           ensure_ascii=False, indent=1))
            log(f"  [{c['cid']} r{round_no} k{k}] seed={seed} "
                f"tok={usage['tokens']} ok={ok} "
                f"{('; '.join(reasons))[:130]}")
            if ok:
                return body, dict(round=round_no, k=k, seed=seed,
                                  tokens=usage["tokens"])
        own_prev = comp
        feedback = "last sample rejected: " + "; ".join(reasons)
    return None, {}


def main() -> None:
    t0 = time.time()
    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    log(f"model loaded in {time.time() - t0:.0f}s")

    # states.tsx is assembled from up to three accepted parts; parts
    # already accepted in an earlier run are picked up from the archive
    states_parts: dict[str, str] = {}
    states_meta: dict[str, dict] = {}
    accepted_files: dict[str, str] = {}

    for c in UI_CONTRACTS:
        log(f"== {c['cid']} ({c['file']} :: {c['part']}) ==")
        body, meta = gen_ui(model, c)
        if body is None:
            log(f"  {c['cid']} FAILED 3x4 — recorded for teacher")
            continue
        if c["file"].endswith("states.tsx"):
            states_parts[c["part"]] = body
            states_meta[c["part"]] = meta
        else:
            accepted_files[c["file"]] = body

    usage = dict(model.usage())
    log(f"model usage this run: {usage}")
    del model
    gc.collect()
    time.sleep(2)

    # ---- install ------------------------------------------------------
    install_log = {}
    if states_parts:
        # assemble states.tsx: shared 'use client' + union of imports is
        # NOT authored by the teacher — each part keeps its own head and
        # the parts are concatenated with the duplicate heads removed
        # mechanically (first head kept, later 'use client' + import
        # lines dropped as duplicates)
        heads = []
        bodies = []
        for part in ("EmptyState", "NoMatchesState", "ErrorState"):
            if part not in states_parts:
                continue
            text = states_parts[part]
            lines = text.splitlines()
            head = []
            rest = []
            for ln in lines:
                if (ln.startswith("'use client'")
                        or ln.startswith("import ")
                        or ln.strip() == ""):
                    head.append(ln)
                else:
                    rest.append(ln)
            heads.append(head)
            bodies.append("\n".join(rest).rstrip())
        all_imports = []
        seen = set()
        for h in heads:
            for ln in h:
                if ln.strip() and ln not in seen:
                    seen.add(ln)
                    all_imports.append(ln)
        states_file = ("\n".join(all_imports) + "\n\n"
                       + "\n\n".join(bodies) + "\n")
        target = install.APP / "src/components/stockpilot/states.tsx"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(states_file)
        (GEN / "ui_states_assembled.tsx").write_text(states_file)
        install_log["states.tsx"] = dict(parts=states_meta,
                                         note="three single-component "
                                              "contracts concatenated "
                                              "mechanically")
    for fpath, body in accepted_files.items():
        target = install.APP / fpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body if body.endswith("\n") else body + "\n")

    # ---- gates on whatever is installed --------------------------------
    gate_results = {}
    for contract in CONTRACTS:
        cid = contract["id"]
        if cid not in ("states", "stats", "toolbar", "table", "form",
                       "hook", "page"):
            continue
        fpath = contract["file"]
        if not (install.APP / fpath).exists():
            gate_results[cid] = dict(ok=False, missing=True)
            continue
        ok, fb = runner_d.run_gates(contract, True)
        gate_results[cid] = dict(ok=ok, feedback=fb[:400])
        log(f"GATES {cid}: ok={ok}")
        if not ok:
            log("  feedback: " + fb[:400].replace("\n", "\n  "))

    # ---- ledger ---------------------------------------------------------
    data = json.loads(LEDGER.read_text()) if LEDGER.exists() else \
        {"files": {}, "stages": [], "model_usage_cumulative": {}}
    for c in UI_CONTRACTS:
        if c["file"].endswith("states.tsx"):
            if c["part"] in states_meta:
                data["files"].setdefault(
                    "src/components/stockpilot/states.tsx", {})[
                    c["part"]] = states_meta[c["part"]]
        elif c["file"] in accepted_files:
            data["files"][c["file"]] = dict(
                contract=c["cid"], label="QWEN-ORIGINAL",
                **_meta_for(c, accepted_files))
    data["stages"].append(dict(
        contract="ui-round2", gates=gate_results, usage_run=usage,
        installed=list(install_log.keys()) + list(accepted_files.keys()),
        note=("per-component contracts with neutral-label demos after "
              "the whole-file demo-label-trap diagnosis")))
    c2 = data.setdefault("model_usage_cumulative", {})
    c2["generations"] = c2.get("generations", 0) + usage["generations"]
    c2["total_new_tokens"] = (c2.get("total_new_tokens", 0)
                              + usage["total_new_tokens"])
    LEDGER.write_text(json.dumps(data, indent=1))

    devserver.start_dev()
    log(f"ui-round2 complete in {time.time() - t0:.0f}s")


def _meta_for(c: dict, accepted_files: dict) -> dict:
    return dict(part=c["part"], src=f"{c['cid']}_r*_k*.json")


if __name__ == "__main__":
    main()
