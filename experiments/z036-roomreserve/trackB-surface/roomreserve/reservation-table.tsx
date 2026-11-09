export function ReservationTable(

  props: {
    rows: { id: string; roomName: string; title: string; organizer: string; start: string; end: string; status: string }[]
    onEdit: (id: string) => void
    onCancel: (id: string) => void
  }
) {
  return (
    <div className="mb-5">
      <table className="hidden w-full text-sm md:table">
        <thead><tr><th>Room</th><th>Title</th><th>Organizer</th><th>Start</th><th>End</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          {props.rows.map((r) => (
            <tr key={r.id}>
              <td>{r.roomName}</td><td>{r.title}</td><td>{r.organizer}</td><td>{r.start}</td><td>{r.end}</td>
              <td><span>{r.status}</span></td>
              <td>
                <button onClick={() => props.onEdit(r.id)}>Edit</button>
                <button onClick={() => props.onCancel(r.id)}>Cancel</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="space-y-2 md:hidden">
        {props.rows.map((r) => (
          <li key={r.id} className="rounded-md border p-3">
            <p className="font-medium">{r.title}</p>
            <p className="text-sm text-muted-foreground">{r.organizer} · {r.start} - {r.end}</p>
            <div className="mt-2 flex gap-2">
              <button onClick={() => props.onEdit(r.id)}>Edit</button>
              <button onClick={() => props.onCancel(r.id)}>Cancel</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}