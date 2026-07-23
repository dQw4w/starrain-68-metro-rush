import { useCallback, useRef, useState } from 'react'

export interface ToastMessage {
  id: number
  team_name: string
  message: string
  chip_delta?: number | null
}

/** Queues transient toasts (auto-dismiss after 4s), fed by WS `activity_log` events. */
export function useToastQueue() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const counter = useRef(0)

  const push = useCallback((t: Omit<ToastMessage, 'id'>) => {
    const id = ++counter.current
    setToasts((cur) => [...cur, { ...t, id }])
    setTimeout(() => setToasts((cur) => cur.filter((x) => x.id !== id)), 4000)
  }, [])

  return { toasts, push }
}

export default function ToastStack({ toasts }: { toasts: ToastMessage[] }) {
  if (toasts.length === 0) return null
  return (
    <div className="fixed top-3 right-3 z-[3000] flex flex-col gap-2 max-w-xs pointer-events-none">
      {toasts.map((t) => (
        <div key={t.id} className="bg-slate-800/95 border border-white/10 rounded-lg px-3 py-2 text-sm shadow-lg">
          <div className="font-bold text-white/90">{t.team_name}</div>
          <div className="text-white/70">{t.message}</div>
          {t.chip_delta != null && (
            <div className={t.chip_delta >= 0 ? 'text-emerald-400 text-xs' : 'text-rose-400 text-xs'}>
              {t.chip_delta >= 0 ? '+' : ''}
              {t.chip_delta} 枚
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
