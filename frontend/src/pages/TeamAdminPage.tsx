import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import ActionLogList from '../components/ActionLogList'
import GameClock from '../components/GameClock'
import MetroMap from '../components/MetroMap'
import { usePhase } from '../hooks/usePhase'
import { useWebSocket, type WsEvent } from '../hooks/useWebSocket'
import { clearAdminSession, loadAdminSession } from '../lib/adminSession'
import type { ActionLogEntry, ApprovalRequest, ChallengeTeaser, DevicePosition, MapData, TeamPublic } from '../types'

const KIND_LABELS: Record<string, string> = {
  claim: '佔領車站',
  topup: '車站加碼',
  challenge_start: '任務開始',
  challenge_result: '任務結果判定',
}

export default function TeamAdminPage() {
  const { teamId: teamIdParam } = useParams<{ teamId: string }>()
  const teamId = Number(teamIdParam)
  const navigate = useNavigate()
  const session = loadAdminSession()

  const [teamInfo, setTeamInfo] = useState<TeamPublic | null>(null)
  const [pending, setPending] = useState<ApprovalRequest[]>([])
  const [log, setLog] = useState<ActionLogEntry[]>([])
  const [gps, setGps] = useState<DevicePosition[]>([])
  const [mapData, setMapData] = useState<MapData | null>(null)
  const [challenges, setChallenges] = useState<ChallengeTeaser[]>([])
  const [tab, setTab] = useState<'queue' | 'log' | 'gps' | 'adjust'>('queue')
  const [error, setError] = useState('')
  const { phase, refetchPhase } = usePhase()

  useEffect(() => {
    if (!session || (!session.is_super && session.team_id !== teamId)) {
      navigate('/admin/login')
    }
  }, [session, teamId, navigate])

  const token = session?.token || ''

  const refresh = useCallback(async () => {
    if (!token || !teamId) return
    const [info, pend, l, g] = await Promise.all([
      api.adminTeamInfo(token, teamId),
      api.adminPending(token, teamId),
      api.adminLog(token, teamId),
      api.adminGps(token, teamId),
    ])
    setTeamInfo(info)
    setPending(pend)
    setLog(l)
    setGps(g)
  }, [token, teamId])

  useEffect(() => {
    refresh()
    api.getMap().then(setMapData).catch(() => {})
    api.getActiveChallenges().then(setChallenges).catch(() => {})
  }, [refresh])

  const getTicket = useCallback(async () => {
    if (!token) throw new Error('not logged in')
    return (await api.adminWsTicket(token)).ticket
  }, [token])

  const handleWsEvent = useCallback(
    (ev: WsEvent) => {
      if (ev.type === '__connected__') return refresh()
      if (ev.team_id !== undefined && ev.team_id !== teamId) return
      if (['admin_pending', 'team_update', 'gps_update'].includes(ev.type)) refresh()
      if (ev.type === 'map_update') api.getMap().then(setMapData)
      if (ev.type === 'challenge_pool') api.getActiveChallenges().then(setChallenges)
      if (ev.type === 'config_update') refetchPhase()
    },
    [refresh, teamId, refetchPhase]
  )
  useWebSocket(getTicket, handleWsEvent)

  const oldest = pending[0]
  const stationName = useMemo(() => {
    if (!mapData) return (id: number) => `車站 #${id}`
    const byId = new Map(mapData.stations.map((s) => [s.id, s.name_zh]))
    return (id: number) => byId.get(id) || `車站 #${id}`
  }, [mapData])
  const challengeName = useMemo(() => {
    const byId = new Map(challenges.map((c) => [c.id, c.name]))
    return (id: number) => byId.get(id) || `任務 #${id}`
  }, [challenges])

  async function handleApprove(req: ApprovalRequest, body?: { success: boolean; achieved_value?: number }) {
    try {
      await api.adminApprove(token, teamId, req.id, body)
      refresh()
    } catch (e: any) {
      setError(e.message || '操作失敗')
    }
  }

  async function handleDeny(req: ApprovalRequest) {
    try {
      await api.adminDeny(token, teamId, req.id)
      refresh()
    } catch (e: any) {
      setError(e.message || '操作失敗')
    }
  }

  function logout() {
    clearAdminSession()
    navigate('/admin/login')
  }

  if (!session || !teamInfo) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-900 text-white">
        <p>載入中…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 bg-slate-800">
        <span className="w-3.5 h-3.5 rounded-full" style={{ backgroundColor: teamInfo.color_hex }} />
        <h1 className="font-black text-lg flex-1">{teamInfo.name}｜隨隊管理員</h1>
        <span className="text-sm text-white/70">
          {teamInfo.stations_owned} 站 · {teamInfo.chips_balance} 枚
        </span>
        <button onClick={logout} className="text-white/50 text-sm">
          登出
        </button>
        {phase && (
          <div className="w-full">
            <GameClock phase={phase} />
          </div>
        )}
      </header>

      <nav className="flex bg-slate-800/60 border-t border-white/10">
        {(['queue', 'log', 'gps', 'adjust'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2.5 text-sm font-bold relative ${tab === t ? 'text-white bg-white/10' : 'text-white/50'}`}
          >
            {{ queue: '待審核', log: '紀錄', gps: 'GPS', adjust: '調整代幣' }[t]}
            {t === 'queue' && pending.length > 0 && (
              <span className="absolute top-1 right-3 bg-rose-500 text-xs rounded-full w-4 h-4 flex items-center justify-center">
                {pending.length}
              </span>
            )}
          </button>
        ))}
      </nav>

      {error && <div className="bg-rose-600 text-white text-sm p-2 text-center">{error}</div>}

      <main className="flex-1 p-3 overflow-y-auto">
        {tab === 'queue' && (
          <div className="flex flex-col gap-2">
            {pending.length === 0 && <p className="text-white/40 text-center py-8">目前沒有待審核項目</p>}
            {pending.map((req) => (
              <PendingCard
                key={req.id}
                req={req}
                highlighted={req.id === oldest?.id}
                stationName={stationName}
                challengeName={challengeName}
                onApprove={(body) => handleApprove(req, body)}
                onDeny={() => handleDeny(req)}
              />
            ))}
          </div>
        )}

        {tab === 'log' && <ActionLogList entries={log} />}

        {tab === 'gps' && mapData && (
          <div className="h-[70vh] rounded-xl overflow-hidden">
            <MetroMap mapData={mapData} teams={[teamInfo]} gps={gps} />
          </div>
        )}

        {tab === 'adjust' && <AdjustChipsForm onSubmit={async (delta, reason) => {
          await api.adminAdjustChips(token, teamId, delta, reason)
          refresh()
        }} />}
      </main>
    </div>
  )
}

function PendingCard({
  req,
  highlighted,
  stationName,
  challengeName,
  onApprove,
  onDeny,
}: {
  req: ApprovalRequest
  highlighted: boolean
  stationName: (id: number) => string
  challengeName: (id: number) => string
  onApprove: (body?: { success: boolean; achieved_value?: number }) => void
  onDeny: () => void
}) {
  const [achieved, setAchieved] = useState('')

  const subject =
    req.station_id != null
      ? stationName(req.station_id)
      : req.challenge_id != null
        ? challengeName(req.challenge_id)
        : ''

  return (
    <div className={`rounded-xl p-3 ${highlighted ? 'bg-amber-500/20 ring-2 ring-amber-400' : 'bg-white/5'}`}>
      <div className="flex justify-between items-baseline">
        <span className="font-bold">{KIND_LABELS[req.kind]}</span>
        <span className="text-xs text-white/40">{new Date(req.created_at).toLocaleTimeString('zh-TW')}</span>
      </div>
      <p className="text-white/80 text-sm">{subject}</p>
      {(req.kind === 'claim' || req.kind === 'topup') && req.requested_value?.amount != null && (
        <p className="text-sm font-bold text-amber-300">投入枚數：{req.requested_value.amount} 枚</p>
      )}
      {req.requested_value?.called_shot_value != null && (
        <p className="text-xs text-white/50">喊出數量：{req.requested_value.called_shot_value}</p>
      )}
      {req.requested_value?.achieved_value != null && (
        <p className="text-xs text-white/50">回報完成數量：{req.requested_value.achieved_value}</p>
      )}

      {req.kind === 'challenge_result' ? (
        <div className="mt-2 flex flex-col gap-2">
          <input
            type="number"
            placeholder="實際完成數量（可覆蓋隊伍回報值）"
            value={achieved}
            onChange={(e) => setAchieved(e.target.value)}
            className="bg-white/10 rounded-lg px-2 py-1.5 text-sm"
          />
          <div className="flex gap-2">
            <button
              onClick={() => onApprove({ success: true, achieved_value: achieved ? Number(achieved) : undefined })}
              className="flex-1 bg-emerald-600 rounded-lg py-2 font-bold text-sm"
            >
              判定成功
            </button>
            <button
              onClick={() => onApprove({ success: false, achieved_value: achieved ? Number(achieved) : undefined })}
              className="flex-1 bg-rose-600 rounded-lg py-2 font-bold text-sm"
            >
              判定失敗
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex gap-2">
          <button onClick={() => onApprove()} className="flex-1 bg-emerald-600 rounded-lg py-2 font-bold text-sm">
            核准
          </button>
          <button onClick={onDeny} className="flex-1 bg-rose-600 rounded-lg py-2 font-bold text-sm">
            拒絕
          </button>
        </div>
      )}
    </div>
  )
}

function AdjustChipsForm({ onSubmit }: { onSubmit: (delta: number, reason: string) => Promise<void> }) {
  const [delta, setDelta] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSubmit(Number(delta), reason)
          setDelta('')
          setReason('')
        } finally {
          setBusy(false)
        }
      }}
      className="flex flex-col gap-3 max-w-sm"
    >
      <label className="text-sm">
        調整數量（正數增加，負數扣除）
        <input
          type="number"
          value={delta}
          onChange={(e) => setDelta(e.target.value)}
          required
          className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
        />
      </label>
      <label className="text-sm">
        原因
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
        />
      </label>
      <button disabled={busy} className="bg-blue-600 disabled:opacity-40 rounded-lg py-2.5 font-bold">
        送出調整
      </button>
    </form>
  )
}
