import { useEffect, useRef } from 'react'

export interface WsEvent {
  type: string
  team_id?: number
  [key: string]: any
}

/**
 * Connects to the shared /ws endpoint using a fresh short-lived ticket (minted
 * via getTicket) each time we (re)connect. Reconnects with backoff on drop —
 * Taipei MRT stations are frequently underground with poor/no signal, so
 * drops are expected, not exceptional. On every successful (re)connect we
 * call onEvent({type: '__connected__'}) so the caller can do a full
 * authoritative refetch rather than trusting a 20s poll to eventually catch up.
 */
export function useWebSocket(getTicket: () => Promise<string>, onEvent: (event: WsEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    let cancelled = false
    let ws: WebSocket | null = null
    let attempt = 0
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    async function connect() {
      if (cancelled) return
      try {
        const ticket = await getTicket()
        if (cancelled) return
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        ws = new WebSocket(`${proto}://${window.location.host}/ws?ticket=${ticket}`)
        ws.onopen = () => {
          attempt = 0
          onEventRef.current({ type: '__connected__' })
        }
        ws.onmessage = (ev) => {
          try {
            onEventRef.current(JSON.parse(ev.data))
          } catch {
            /* ignore malformed frame */
          }
        }
        ws.onclose = scheduleReconnect
        ws.onerror = () => ws?.close()
      } catch {
        scheduleReconnect()
      }
    }

    function scheduleReconnect() {
      if (cancelled) return
      const delay = Math.min(1000 * 2 ** attempt, 15000)
      attempt += 1
      reconnectTimer = setTimeout(connect, delay)
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
