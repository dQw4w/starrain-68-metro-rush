import { useEffect, useState } from 'react'
import type { MapData, Station, TeamPublic } from '../types'

const LAST_AMOUNT_KEY = 'metro_rush_last_deposit_amount'

function loadLastAmount(): number {
  const raw = localStorage.getItem(LAST_AMOUNT_KEY)
  const n = raw ? Number(raw) : 1
  return Number.isFinite(n) && n > 0 ? n : 1
}

interface Props {
  station: Station
  mapData: MapData
  myTeamId: number
  teams: TeamPublic[]
  hasPendingRequest: boolean
  maxDepositPerVisit: number
  onClose: () => void
  onSubmit: (kind: 'claim' | 'topup', amount: number) => Promise<void>
}

export default function ClaimSheet({
  station,
  mapData,
  myTeamId,
  teams,
  hasPendingRequest,
  maxDepositPerVisit,
  onClose,
  onSubmit,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const claim = mapData.claims.find((c) => c.station_id === station.id)
  const owner = claim?.owner_team_id ? teams.find((t) => t.id === claim.owner_team_id) : undefined
  const isMine = claim?.owner_team_id === myTeamId
  const value = claim?.value ?? 0
  const cap = claim?.cap ?? maxDepositPerVisit
  // Only a top-up can be "maxed out" — claiming always gets a fresh ceiling
  // relative to the current value, so a rival can always take a station away.
  const maxed = isMine && value >= cap
  const kind: 'claim' | 'topup' = isMine ? 'topup' : 'claim'
  const minAmount = isMine ? 1 : value + 1
  const maxAmount = isMine ? cap - value : value + maxDepositPerVisit

  const [amount, setAmount] = useState(() => Math.min(Math.max(minAmount, loadLastAmount()), maxAmount))

  useEffect(() => {
    setAmount(Math.min(Math.max(minAmount, loadLastAmount()), maxAmount))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station.id])

  function clamp(n: number) {
    return Math.min(maxAmount, Math.max(minAmount, n))
  }

  function adjust(delta: number) {
    setAmount((prev) => clamp(prev + delta))
  }

  async function handleSubmit() {
    setBusy(true)
    setError('')
    try {
      await onSubmit(kind, amount)
      localStorage.setItem(LAST_AMOUNT_KEY, String(amount))
    } catch (e: any) {
      setError(e.message || '操作失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[2000] flex items-end sm:items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-slate-800 text-white rounded-t-2xl sm:rounded-2xl w-full sm:max-w-sm p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start mb-2">
          <h2 className="text-xl font-bold">{station.name_zh}</h2>
          <button onClick={onClose} className="text-white/50 text-2xl leading-none">
            &times;
          </button>
        </div>

        {owner ? (
          <p className="text-sm text-white/70 mb-1">
            目前擁有：<span style={{ color: owner.color_hex }}>{owner.name}</span>（{value} / {cap} 枚代幣）
          </p>
        ) : (
          <p className="text-sm text-white/70 mb-1">目前尚未被佔領</p>
        )}

        {error && <p className="text-rose-400 text-sm mt-2">{error}</p>}

        {hasPendingRequest ? (
          <p className="mt-4 text-amber-300 font-medium">⏳ 已送出申請，等待隨隊管理員核准…</p>
        ) : maxed ? (
          <p className="mt-4 text-white/50">此車站代幣數已達上限，無法再變動。</p>
        ) : (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-sm text-white/60">投入枚數（合法範圍：{minAmount} ~ {maxAmount}）</p>
            <div className="flex items-center gap-2">
              <StepButton label="-5" onClick={() => adjust(-5)} disabled={amount - 5 < minAmount} />
              <StepButton label="-1" onClick={() => adjust(-1)} disabled={amount - 1 < minAmount} />
              <input
                type="number"
                inputMode="numeric"
                value={amount}
                onChange={(e) => {
                  const n = Number(e.target.value)
                  if (Number.isFinite(n)) setAmount(clamp(Math.trunc(n)))
                }}
                className="w-20 text-center bg-white/10 rounded-lg py-2 font-bold text-lg tabular-nums"
              />
              <StepButton label="+1" onClick={() => adjust(1)} disabled={amount + 1 > maxAmount} />
              <StepButton label="+5" onClick={() => adjust(5)} disabled={amount + 5 > maxAmount} />
            </div>
            <button disabled={busy} onClick={handleSubmit} className="w-full bg-blue-600 disabled:opacity-40 font-bold rounded-xl py-3">
              {isMine ? '加碼投入代幣' : '佔領此車站'}（需管理員核准）
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function StepButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="bg-white/10 disabled:opacity-30 rounded-lg px-3 py-2 font-bold text-sm shrink-0"
    >
      {label}
    </button>
  )
}
