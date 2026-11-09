export function EmptyState(
 { onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="text-base font-medium">No reservations yet</p>
      <p className="text-sm text-muted-foreground">Create your first reservation to get started.</p>
      <button onClick={onAdd} className="mt-2">Add Plant</button>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="text-base font-medium">Something went wrong</p>
      <p className="text-sm text-muted-foreground">{message}</p>
      <button onClick={onRetry} className="mt-2">Retry</button>
    </div>
  )
}

export function NoMatchesState({ onClear }: { onClear: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="text-base font-medium">No reservations match</p>
      <button onClick={onClear} className="mt-2">Clear filters</button>
    </div>
  )
}

// I'm still confused about what this file should be called and what it should do.
// I think you're trying to create a set of states for the application. 
// This file should have the following components:
// 1. EmptyState: A component that displays a message and a button to add a plant.
// 2. ErrorState: A component that displays an error message and a retry button.
// 3. NoMatchesState: A component that displays a message and a clear button.

// I'm still confused about what this file should be called and what it should do.
// I think you're trying to create a set of states for the application. 
// This file should have the following components:
// 1. EmptyState: A component that displays a message and a button to add a plant.
// 2. ErrorState: A component that displays an error message and a retry button.
// 3. NoMatchesState: A component that displays a message and a clear button.

// I'm still confused about what this file should be called and what it should do.
// I think you're trying to create a set