export function ReservationForm(
 {
  open,
  rooms,
  initialValues,
  onSubmit,
  onClose,
  errorText,
}: {
  open: boolean
  rooms: Room[]
  initialValues: Room
  onSubmit: (values: Room) => void
  onClose: () => void
  errorText: string
}) {

  return (
    <div role="dialog" aria-modal="true" hidden={!open}>
      <div>
        <label htmlFor="f-title">Course</label>
        <select id="f-title">
          {rooms.map(room => (
            <option value={room.id}>{room.name}</option>
          ))}
        </select>
        <label htmlFor="f-coach">Coach</label>
        <select id="f-coach">
          {rooms.map(room => (
            <option value={room.id}>{room.name}</option>
          ))}
        </select>
        <label htmlFor="f-day">Day</label>
        <input id="f-day" type="date" />
        <label htmlFor="f-from">From</label>
        <input id="f-from" type="time" />
        <label htmlFor="f-to">To</label>
        <input id="f-to" type="time" />
        <button type="submit">Save Reservation</button>
      </div>
    </div>
  )

}