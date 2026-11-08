'use client'

// TEACHER-INTEGRATION (Session 035, disclosed): StatsBar failed its
// 3x4 contract budget (12/12 samples — see generations/ui-stats_*.json).
// Frozen interface, labels and layout per SPEC §3.

import { Card, CardContent } from '@/components/ui/card'
import { InventoryItem } from '@/lib/inventory/types'

export function StatsBar({ items }: { items: InventoryItem[] }) {
  const totalItems = items.length
  const totalUnits = items.reduce((sum, i) => sum + i.quantity, 0)
  const lowStock = items.filter(
    (i) => i.quantity > 0 && i.quantity <= i.minQuantity).length
  const outOfStock = items.filter((i) => i.quantity === 0).length
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{totalItems}</div>
          <div className="text-xs text-muted-foreground">Total items</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{totalUnits}</div>
          <div className="text-xs text-muted-foreground">Total units</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{lowStock}</div>
          <div className="text-xs text-muted-foreground">Low stock</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="text-2xl font-semibold tabular-nums">{outOfStock}</div>
          <div className="text-xs text-muted-foreground">Out of stock</div>
        </CardContent>
      </Card>
    </div>
  )
}
