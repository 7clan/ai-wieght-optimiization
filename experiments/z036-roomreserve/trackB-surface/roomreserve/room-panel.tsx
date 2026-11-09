export function RoomPanel(
 { rooms, selectedId, onSelect } ) {
  return (
    <aside className="w-56 shrink-0">
      <h2 className="mb-3 text-sm font-medium">Rooms</h2>
      <button onClick={() => onSelect('')}>All rooms</button>
      <ul className="space-y-1">
        {rooms.map((r) => (
          <li key={r.id}>
            <button
              aria-pressed={selectedId === r.id}
              onClick={() => onSelect(r.id)}
              className={selectedId === r.id ? 'bg-accent' : ''}
            >
              <span>{r.name}</span>
              <span className="text-xs text-muted-foreground">{r.capacity} seats</span>
              <span className="text-xs text-muted-foreground">{r.floor} F</span>
              {r.availability ? 'Available' : 'Booked'}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}