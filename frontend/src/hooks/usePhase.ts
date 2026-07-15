import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { GamePhase } from '../types'

/**
 * Polls the game phase/schedule every 20s so phase-boundary crossings (e.g.
 * entering lunch break) get picked up even without any other WS activity —
 * the second-by-second countdown itself is handled client-side by GameClock
 * ticking locally between refetches.
 */
export function usePhase() {
  const [phase, setPhase] = useState<GamePhase | null>(null)

  const refetch = useCallback(() => {
    api.getPhase().then(setPhase).catch(() => {})
  }, [])

  useEffect(() => {
    refetch()
    const id = setInterval(refetch, 20000)
    return () => clearInterval(id)
  }, [refetch])

  return { phase, refetchPhase: refetch }
}
