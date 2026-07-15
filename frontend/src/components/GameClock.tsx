import { useEffect, useMemo, useState } from 'react'
import type { GamePhase } from '../types'

const STATUS: Record<GamePhase['phase'], { text: string; dot: string; pulse: boolean }> = {
  not_started: { text: '尚未開始', dot: 'bg-gray-400', pulse: false },
  active: { text: '遊戲進行中', dot: 'bg-emerald-500', pulse: true },
  lunch_break: { text: '午休中，暫停操作', dot: 'bg-amber-400', pulse: true },
  ended: { text: '遊戲已結束', dot: 'bg-rose-500', pulse: false },
  paused: { text: '遊戲已暫停', dot: 'bg-rose-500', pulse: false },
}

function formatHMS(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const hh = String(Math.floor(totalSeconds / 3600)).padStart(2, '0')
  const mm = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0')
  const ss = String(totalSeconds % 60).padStart(2, '0')
  return `${hh}小時${mm}分鐘${ss}秒`
}

export default function GameClock({ phase, compact }: { phase: GamePhase; compact?: boolean }) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Correct for the viewer's local clock being off from the server, using the
  // server_time snapshot from the last phase fetch as the reference point.
  const offsetMs = useMemo(() => new Date(phase.server_time).getTime() - Date.now(), [phase.server_time])
  const nowMs = Date.now() + offsetMs

  const startMs = new Date(phase.start_at).getTime()
  const lunchStartMs = new Date(phase.lunch_start_at).getTime()
  const lunchEndMs = new Date(phase.lunch_end_at).getTime()
  const endMs = new Date(phase.end_at).getTime()

  let countdownLabel: string | null = null
  let targetMs = 0
  if (phase.phase === 'not_started') {
    countdownLabel = '距離開始還有'
    targetMs = startMs
  } else if (phase.phase === 'active' && nowMs < lunchStartMs) {
    countdownLabel = '距離午休還有'
    targetMs = lunchStartMs
  } else if (phase.phase === 'active') {
    countdownLabel = '距離結束還有'
    targetMs = endMs
  } else if (phase.phase === 'lunch_break') {
    countdownLabel = '距離午休結束還有'
    targetMs = lunchEndMs
  }

  const status = STATUS[phase.phase]

  return (
    <div className={`flex items-center gap-2 ${compact ? '' : 'flex-wrap'}`}>
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        {status.pulse && <span className={`absolute inline-flex h-full w-full rounded-full ${status.dot} opacity-60 animate-ping`} />}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${status.dot}`} />
      </span>
      <span className="text-sm font-bold">{status.text}</span>
      {countdownLabel && (
        <span className="text-sm text-white/70 tabular-nums">
          {countdownLabel} {formatHMS(targetMs - nowMs)}
        </span>
      )}
    </div>
  )
}
