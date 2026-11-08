'use client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

export function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <Card>
      <CardContent className="p-6 text-center">
        <div className="text-2xl font-semibold tabular-nums">No items yet</div>
        <p className="mt-1 text-sm text-muted-foreground">Add your first item to start tracking stock.</p>
        <div className="flex items-center justify-center mt-2">
          <Button onClick={onAdd}>Add Item</Button>
        </div>
      </CardContent>
    </Card>
  )
}

// TEACHER-INTEGRATION (Session 035, disclosed): NoMatchesState failed
// its 3x4 contract budget (see generations/ui-nomatch_*.json —
// 12/12 samples missing the frozen strings or hallucinating
// redux/recoil imports).  The other two components in this file are
// unmodified Qwen output (ui-empty r0 k3, ui-error r0 k2); this
// teacher part follows the same frozen interface and strings.
// [test-bug fix #9, disclosed: the frozen uitest drives the filters
// via getByLabel(...).selectOption(...), which requires native
// <select> elements with <label>s; the contract text asked for
// radix Selects, which do not support selectOption.  SPEC §3 says
// only "select"; the frozen tests win.]


export function NoMatchesState({ onClear }: { onClear: () => void }) {
  return (
    <Card>
      <CardContent className="p-10 text-center">
        <h3 className="text-lg font-semibold">No items match</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Try a different search term or clear the filters.
        </p>
        <Button variant="outline" className="mt-4" onClick={onClear}>
          Clear filters
        </Button>
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
        <p className="mt-1 text-sm text-muted-foreground">{message}</p>
        <Button onClick={onRetry}>Retry</Button>
      </CardContent>
    </Card>
  )
}
