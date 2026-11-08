'use client'

// TEACHER-INTEGRATION (Session 035, disclosed): ItemTable failed its
// 3x4 contract budget (see generations/ui-table_*.json once complete).
// Frozen interface, columns, badge rules and responsive layout per
// SPEC §3 (desktop table hidden on small screens; stacked cards on
// mobile with the same information).

import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { InventoryItem, stockStatus } from '@/lib/inventory/types'

function StatusBadge({ item }: { item: InventoryItem }) {
  const s = stockStatus(item.quantity, item.minQuantity)
  if (s === 'out of stock') {
    return <Badge variant="destructive">Out of stock</Badge>
  }
  if (s === 'low stock') {
    return (
      <Badge variant="outline" className="border-amber-500/50 text-amber-700">
        Low stock
      </Badge>
    )
  }
  return <Badge>In stock</Badge>
}

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

export function ItemTable({ items, onEdit, onDelete }:
  {
    items: InventoryItem[]
    onEdit: (item: InventoryItem) => void
    onDelete: (item: InventoryItem) => void
  }) {
  return (
    <div>
      <div className="hidden md:block rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>SKU</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Quantity</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {item.sku ?? '—'}
                </TableCell>
                <TableCell>{item.category}</TableCell>
                <TableCell className="tabular-nums">{item.quantity}</TableCell>
                <TableCell><StatusBadge item={item} /></TableCell>
                <TableCell className="text-muted-foreground">
                  {shortDate(item.updatedAt)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost" size="icon" title="Edit" aria-label="Edit"
                    onClick={() => onEdit(item)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost" size="icon" title="Delete"
                    aria-label="Delete"
                    onClick={() => onDelete(item)}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="md:hidden grid gap-3">
        {items.map((item) => (
          <Card key={item.id}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium">{item.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {item.sku ?? '—'} · {item.category}
                  </div>
                </div>
                <StatusBadge item={item} />
              </div>
              <div className="mt-2 text-sm">
                Quantity: <span className="tabular-nums">{item.quantity}</span>
                <span className="text-muted-foreground">
                  {' '}(min {item.minQuantity})
                </span>
              </div>
              <div className="mt-2 flex gap-2">
                <Button variant="outline" size="sm" onClick={() => onEdit(item)}>
                  Edit
                </Button>
                <Button variant="outline" size="sm" onClick={() => onDelete(item)}>
                  Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
