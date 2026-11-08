'use client'

// TEACHER-INTEGRATION (Session 035, disclosed): useInventory failed
// its 3x4 contract budget (see generations/ui-hook_*.json once
// complete).  Frozen interface and behaviors per SPEC §3 and the
// hook contract (debounced filtered fetch, save/remove, reload).

import { useCallback, useEffect, useState } from 'react'
import { InventoryItem, InventoryInput } from '@/lib/inventory/types'

async function getJson(res: Response) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'request failed' }))
    throw new Error(body.error)
  }
  return res.json()
}

export function useInventory() {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('all')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState('updatedAt')
  const [order, setOrder] = useState('desc')
  const [reloadKey, setReloadKey] = useState(0)

  const patch = useCallback((partial: Partial<{
    q: string; category: string; status: string; sort: string;
    order: string }>) => {
    if (partial.q !== undefined) setQ(partial.q)
    if (partial.category !== undefined) setCategory(partial.category)
    if (partial.status !== undefined) setStatus(partial.status)
    if (partial.sort !== undefined) setSort(partial.sort)
    if (partial.order !== undefined) setOrder(partial.order)
  }, [])

  useEffect(() => {
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams()
        if (q) params.set('q', q)
        if (category && category !== 'all') params.set('category', category)
        if (status && status !== 'all') params.set('status', status)
        if (sort && sort !== 'updatedAt') params.set('sort', sort)
        if (order && order !== 'desc') params.set('order', order)
        const qs = params.toString()
        const data = await getJson(
          await fetch(`/api/items${qs ? `?${qs}` : ''}`))
        setItems(data.items)
        setError(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'failed to load')
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [q, category, status, sort, order, reloadKey])

  const reload = useCallback(() => {
    setReloadKey((k) => k + 1)
  }, [])

  const saveItem = useCallback(async (input: InventoryInput, id?: string) => {
    const res = await fetch(id ? `/api/items/${id}` : '/api/items', {
      method: id ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: input.name,
        category: input.category,
        sku: input.sku,
        quantity: input.quantity,
        minQuantity: input.minQuantity,
      }),
    })
    await getJson(res)
    await reload()
  }, [reload])

  const removeItem = useCallback(async (id: string) => {
    const res = await fetch(`/api/items/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      throw new Error('failed to delete')
    }
    await reload()
  }, [reload])

  return {
    items, loading, error, reload, patch,
    q, category, status, sort, order, saveItem, removeItem,
  }
}
