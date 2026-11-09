'use client'

import { useCallback, useEffect, useState } from 'react'

export function useReservations({ date, roomId, includeCancelled }: { date: string; roomId: string; includeCancelled: boolean }) {
  const [reservations, setReservations] = useState([])
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    fetch('/api/reservations', {
      method: 'POST',
      body: JSON.stringify({ date, roomId, includeCancelled }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject('load failed')))
      .then((d) => { if (d.error) { setError(d.error) } else { setReservations(d.reservations) } })
      .catch(() => { setError('Could not load reservations') })
      .finally(() => { if (loading) setLoading(false) })
  }, [reloadKey, roomId, date, includeCancelled])

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])
  return { reservations, loading, error, reload }
}