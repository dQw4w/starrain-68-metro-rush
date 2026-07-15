import { useMemo, useState } from 'react'
import type { ActionLogEntry } from '../types'

const TYPE_LABELS: Record<string, string> = {
  claim: '佔領車站',
  topup: '車站加碼',
  toll_paid: '支付通行費',
  toll_received: '收到通行費',
  challenge_start_approved: '任務開始',
  challenge_result: '任務結果',
  challenge_stolen: '被偷代幣',
  challenge_auto_failed: '任務逾時失敗',
  admin_adjust: '管理員調整',
}

export default function ActionLogList({ entries }: { entries: ActionLogEntry[] }) {
  const [filter, setFilter] = useState('all')

  const types = useMemo(() => Array.from(new Set(entries.map((e) => e.action_type))), [entries])
  const filtered = filter === 'all' ? entries : entries.filter((e) => e.action_type === filter)

  return (
    <div className="flex flex-col gap-2">
      <select
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="bg-white/10 text-white text-sm rounded-lg px-2 py-1.5 self-start"
      >
        <option value="all">全部紀錄</option>
        {types.map((t) => (
          <option key={t} value={t}>
            {TYPE_LABELS[t] || t}
          </option>
        ))}
      </select>
      <div className="flex flex-col gap-1.5 max-h-full overflow-y-auto">
        {filtered.length === 0 && <p className="text-white/40 text-sm py-4 text-center">尚無紀錄</p>}
        {filtered.map((e) => (
          <div key={e.id} className="bg-white/5 rounded-lg px-3 py-2 text-sm">
            <div className="flex justify-between items-baseline gap-2">
              <span className="font-medium text-white">{TYPE_LABELS[e.action_type] || e.action_type}</span>
              <span className="text-white/40 text-xs shrink-0">
                {new Date(e.created_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            <div className="text-white/70">{e.message}</div>
            {e.chip_delta != null && (
              <div className={e.chip_delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {e.chip_delta >= 0 ? '+' : ''}
                {e.chip_delta} 枚（餘額 {e.resulting_balance}）
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
