'use client'
import type { Dispatch, SetStateAction } from 'react';
import { useEffect, useState } from 'react';
import { useQuery } from 'react-query';

export const useReservations = (
  params: {
    date: string;
    roomId: string;
    includeCancelled?: boolean;
  },
) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reservations, setReservations] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [reloadKey, setReloadKey] = useState(0);

  const fetchReservations = async (date: string, roomId: string, includeCancelled: boolean) => {
    setLoading(true);
    const url = '/api/rooms';
    const options = {
      method: 'POST',
      body: JSON.stringify({
        date,
        roomId,
        includeCancelled,
      }),
    };

    try {
      const response = await fetch(url, options);
      if (response.ok) {
        const data = await response.json();
        setReservations(data.reservations);
        setRooms(data.rooms);
      } else {
        setError('Could not load reservations');
      }
    } catch (error) {
      setError('Could not load reservations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReservations(params.date, params.roomId, params.includeCancelled);
  }, [params.date, params.roomId, params.includeCancelled]);

  const reload = useCallback(() => {
    setReloadKey((prev) => prev + 1);
  }, []);

  return {
    reservations,
    rooms,
    loading,
    error,
    reload,
  };
};
