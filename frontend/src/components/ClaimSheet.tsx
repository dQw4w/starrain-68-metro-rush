import { useState } from 'react'
import type { MapData, Station, TeamPublic } from '../types'

interface Props {
  station: Station
  mapData: MapData
  myTeamId: number
  teams: TeamPublic[]
  hasPendingRequest: boolean
  onClose: () => void
  onSubmit: (kind: 'claim' | 'topup') => Promise<void>
}

export default function ClaimSheet({ station, mapData, myTeamId, teams, hasPendingRequest, onClose, onSubmit }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const claim = mapData.claims.find((c) => c.station_id === station.id)
  const owner = claim?.owner_team_id ? teams.find((t) => t.id === claim.owner_team_id) : undefined
  const isMine = claim?.owner_team_id === myTeamId
  const value = claim?.value ?? 0
  const maxed = value >= 5
  const kind: 'claim' | 'topup' = isMine ? 'topup' : 'claim'
  const estimatedCost = value + 1

  async function handleSubmit() {
    setBusy(true)
    setError('')
    try {
      await onSubmit(kind)
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
            目前擁有：<span style={{ color: owner.color_hex }}>{owner.name}</span>（{value} 枚代幣）
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
          <div className="mt-4">
            <p className="text-sm text-white/60 mb-3">
              預估花費：約 {estimatedCost} 枚代幣（實際金額將由系統於核准當下重新計算）
            </p>
            <button disabled={busy} onClick={handleSubmit} className="w-full bg-blue-600 disabled:opacity-40 font-bold rounded-xl py-3">
              {isMine ? '加碼投入代幣' : '佔領此車站'}（需管理員核准）
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
