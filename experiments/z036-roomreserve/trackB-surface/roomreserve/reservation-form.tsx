export function ReservationForm(

  { open, onClose, rooms, initialValues, errorText, onSubmit, onClose }: {
    open: boolean
    onClose: () => void
    rooms: { id: number; name: string }[]
    initialValues: {
      roomId: number
      title: string
      organizer: string
      date: string
      start: string
      end: string
    }
    errorText?: string
    onSubmit: (values: { roomId: number; title: string; organizer: string; date: string; start: string; end: string }) => void
    onClose: () => void
  }) {
  const [error, setError] = React.useState<string | null>(null)
  const [values, setValues] = React.useState(initialValues)

  React.useEffect(() => {
    if (errorText) setError(errorText)
  }, [errorText])

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    setValues((prevValues) => ({
      ...prevValues,
      [name]: value
    }))
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    onSubmit(values)
    onClose()
  }

  return (
    <form onSubmit={handleSubmit} role="dialog" aria-modal="true">
      <div hidden={!open}>
        <h2>Room Reservation</h2>
        <ul>
          <li>
            <label htmlFor="f-room">Room</label>
            <select id="f-room" name="roomId">
              {rooms.map((room) => (
                <option value={room.id} key={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          </li>
          <li>
            <label htmlFor="f-title">Title</label>
            <input id="f-title" name="title" type="text" value={values.title} onChange={handleChange} />
          </li>
          <li>
            <label htmlFor="f-organizer">Organizer</label>
            <input id="f-organizer" name="organizer" type="text" value={values.organizer} onChange={handleChange} />
          </li>
          <li>
            <label htmlFor="f-date">Date</label>
            <input id="f-date" name="date" type="date" value={values.date} onChange={handleChange} />
          </li>
          <li>
            <label htmlFor="f-start">Start Time</label>
            <input id="f-start" name="start" type="time" value={values.start} onChange={handleChange} />
          </li>
          <li>
            <label htmlFor="f-end">End Time</label>
            <input id="f-end" name="end" type="time" value={values.end} onChange={handleChange} />
          </li>
          <li>
            <button type="submit" disabled={errorText ? true : false}>
              Save Reservation
            </button>
          </li>
        </ul>
        <h3>Errors</h3>
        <p>{error}</p>
      </div>
    </form>
  )
}