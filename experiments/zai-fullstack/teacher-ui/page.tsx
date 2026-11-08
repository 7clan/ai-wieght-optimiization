'use client'

// TEACHER-INTEGRATION (Session 035, disclosed): the page assembly
// failed its 3x4 contract budget (see generations/ui-page_*.json
// once complete).  Frozen layout, strings and state machine per
// SPEC §3; assembles the model-generated and teacher components
// behind their frozen interfaces.

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState, NoMatchesState, ErrorState }
  from '@/components/stockpilot/states'
import { StatsBar } from '@/components/stockpilot/stats-bar'
import { Toolbar } from '@/components/stockpilot/toolbar'
import { ItemTable } from '@/components/stockpilot/item-table'
import { ItemForm } from '@/components/stockpilot/item-form'
import { useInventory } from '@/lib/inventory/use-inventory'
import { InventoryItem } from '@/lib/inventory/types'

export default function Home() {
  const {
    items, loading, error, reload, patch,
    q, category, status, sort, order, saveItem, removeItem,
  } = useInventory()
  const [formOpen, setFormOpen] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const [editing, setEditing] = useState<InventoryItem | null>(null)
  const [confirmItem, setConfirmItem] = useState<InventoryItem | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const categories = [...new Set(items.map((i) => i.category))].sort()

  useEffect(() => {
    if (toast === null) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  function showToast(message: string) {
    setToast(message)
  }

  function openForm(item: InventoryItem | null) {
    setEditing(item)
    setFormKey((k) => k + 1)
    setFormOpen(true)
  }

  async function handleSaved(input: Parameters<typeof saveItem>[0]) {
    try {
      await saveItem(input, editing?.id)
      setFormOpen(false)
      showToast(editing ? 'Item updated' : 'Item added')
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Save failed')
    }
  }

  async function handleDelete() {
    if (!confirmItem) return
    try {
      await removeItem(confirmItem.id)
      setConfirmItem(null)
      showToast('Item deleted')
    } catch (e) {
      setConfirmItem(null)
      showToast(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">StockPilot</h1>
            <p className="text-sm text-muted-foreground">
              Track stock levels, categories and low-stock alerts
            </p>
          </div>
          <Button onClick={() => openForm(null)}>
            Add Item
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <div className="grid gap-6">
          <StatsBar items={items} />
          <Toolbar
            q={q} category={category} status={status} sort={sort}
            order={order} categories={categories} onChange={patch}
          />
          <section aria-label="Items">
            {error ? (
              <ErrorState message={error} onRetry={reload} />
            ) : loading ? (
              <div role="status" className="py-16 text-center text-sm text-muted-foreground">
                Loading items…
              </div>
            ) : items.length === 0 && q === '' && category === 'all' && status === 'all' ? (
              <EmptyState onAdd={() => openForm(null)} />
            ) : items.length === 0 ? (
              <NoMatchesState onClear={() => patch({ q: '', category: 'all', status: 'all' })} />
            ) : (
              <ItemTable
                items={items}
                onEdit={(item) => openForm(item)}
                onDelete={(item) => setConfirmItem(item)}
              />
            )}
          </section>
        </div>
      </main>

      <footer className="mt-auto border-t">
        <div className="mx-auto max-w-5xl px-4 py-4 text-xs text-muted-foreground">
          StockPilot — inventory management demo
        </div>
      </footer>

      <ItemForm
        key={formKey}
        open={formOpen}
        initial={editing}
        onClose={() => setFormOpen(false)}
        onSaved={handleSaved}
      />

      <Dialog open={confirmItem !== null}
        onOpenChange={(v) => !v && setConfirmItem(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete item</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete
            {' '}{confirmItem?.name}?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmItem(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-4 right-4 z-50 rounded-md border bg-card px-4 py-2 text-sm shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  )
}
