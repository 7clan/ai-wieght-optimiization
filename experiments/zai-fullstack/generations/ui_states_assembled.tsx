'use client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Card } from '@/components/ui/card'

export function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <Card>
      <CardContent className="p-6 text-center">
        <div className="text-2xl font-semibold tabular-nums">No items yet</div>
        <div className="text-xs text-muted-foreground">Label text</div>
        <div className="flex items-center justify-center mt-2">
          <Button onClick={onAdd}>Add Item</Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function ErrorState({ message, onRetry }:
{ message: string; onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="p-6 text-center">
        <div className="text-2xl font-semibold tabular-nums">Error</div>
        <div className="text-xs text-muted-foreground">Error text</div>
        <Button onClick={onRetry}>Retry</Button>
      </CardContent>
    </Card>
  )
}
