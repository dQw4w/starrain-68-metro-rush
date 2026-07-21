import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import ActionLogList from '../components/ActionLogList'
import ChallengeModal from '../components/ChallengeModal'
import ClaimSheet from '../components/ClaimSheet'
import GameClock from '../components/GameClock'
import MetroMap from '../components/MetroMap'
import RankingBoard from '../components/RankingBoard'
import { useWebSocket, type WsEvent } from '../hooks/useWebSocket'
import { getDeviceId } from '../lib/adminSession'
import type {
  ActionLogEntry,
  Challenge,
  ChallengeAttempt,
  ChallengeTeaser,
  DevicePosition,
  MapData,
  Station,
  TeamState,
} from '../types'

type Tab = 'ranking' | 'challenges' | 'log'

export default function TeamPage() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<TeamState | null>(null)
  const [mapData, setMapData] = useState<MapData | null>(null)
  const [challenges, setChallenges] = useState<ChallengeTeaser[]>([])
  const [log, setLog] = useState<ActionLogEntry[]>([])
  const [gps, setGps] = useState<DevicePosition[]>([])
  const [myAttempts, setMyAttempts] = useState<ChallengeAttempt[]>([])
  const [tab, setTab] = useState<Tab>('ranking')
  const [selectedStation, setSelectedStation] = useState<Station | null>(null)
  const [selectedChallenge, setSelectedChallenge] = useState<ChallengeTeaser | null>(null)
  const [challengeDetail, setChallengeDetail] = useState<Challenge | null>(null)
  const [maxDepositPerVisit, setMaxDepositPerVisit] = useState(5)

  const refreshState = useCallback(async () => {
    if (!token) return
    setState(await api.teamState(token))
  }, [token])
  const refreshMap = useCallback(async () => setMapData(await api.getMap()), [])
  const refreshChallenges = useCallback(async () => setChallenges(await api.getActiveChallenges()), [])
  const refreshConfig = useCallback(async () => {
    const cfg = await api.getPublicConfig()
    setMaxDepositPerVisit(cfg.max_deposit_per_visit)
  }, [])
  const refreshLog = useCallback(async () => {
    if (token) setLog(await api.teamLog(token))
  }, [token])
  const refreshGps = useCallback(async () => {
    if (token) setGps(await api.teamGps(token))
  }, [token])
  const refreshAttempts = useCallback(async () => {
    if (token) setMyAttempts(await api.myAttempts(token))
  }, [token])

  const refreshAll = useCallback(() => {
    refreshState()
    refreshMap()
    refreshChallenges()
    refreshLog()
    refreshGps()
    refreshAttempts()
    refreshConfig()
  }, [refreshState, refreshMap, refreshChallenges, refreshLog, refreshGps, refreshAttempts, refreshConfig])

  useEffect(() => {
    refreshAll()
  }, [refreshAll])

  // Safety net so a phase-boundary crossing (e.g. lunch break starting) is
  // reflected even if nothing else happens to trigger a WS-driven refresh.
  useEffect(() => {
    const id = setInterval(refreshState, 20000)
    return () => clearInterval(id)
  }, [refreshState])

  const getTicket = useCallback(async () => {
    if (!token) throw new Error('no token')
    return (await api.teamWsTicket(token)).ticket
  }, [token])

  const handleWsEvent = useCallback(
    (ev: WsEvent) => {
      if (ev.type === '__connected__') return refreshAll()
      if (ev.type === 'map_update') refreshMap()
      if (ev.type === 'ranking_update') refreshState()
      if (ev.type === 'team_update') {
        refreshState()
        refreshLog()
        refreshAttempts()
      }
      if (ev.type === 'challenge_pool') refreshChallenges()
      if (ev.type === 'gps_update') refreshGps()
      if (ev.type === 'config_update') {
        refreshState()
        refreshConfig()
      }
    },
    [refreshAll, refreshMap, refreshState, refreshLog, refreshAttempts, refreshChallenges, refreshGps, refreshConfig]
  )
  useWebSocket(getTicket, handleWsEvent)

  // Send this device's GPS position periodically.
  useEffect(() => {
    if (!token || !('geolocation' in navigator)) return
    const deviceId = getDeviceId()
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        api.gpsPing(token, deviceId, pos.coords.latitude, pos.coords.longitude).catch(() => {})
      },
      () => {},
      { enableHighAccuracy: false, maximumAge: 15000, timeout: 10000 }
    )
    return () => navigator.geolocation.clearWatch(watchId)
  }, [token])

  useEffect(() => {
    if (!token || !selectedChallenge) return
    setChallengeDetail(null)
    api
      .challengeDetail(token, selectedChallenge.id)
      .then(setChallengeDetail)
      .catch(() => setChallengeDetail(null))
  }, [token, selectedChallenge])

  if (!token) return null
  if (!state || !mapData) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-900 text-white">
        <p>載入中…</p>
      </div>
    )
  }

  const myTeam = state.team
  const pendingStationRequest = state.pending_requests.find(
    (r) => (r.kind === 'claim' || r.kind === 'topup') && r.station_id === selectedStation?.id
  )
  const pendingChallengeRequest = state.pending_requests.find(
    (r) => r.kind === 'challenge_start' && r.challenge_id === selectedChallenge?.id
  )
  const selectedAttempt = myAttempts.find((a) => a.challenge_id === selectedChallenge?.id)

  async function submitClaim(kind: 'claim' | 'topup', amount: number) {
    if (!token || !selectedStation) return
    await api.teamAction(token, selectedStation.id, kind, amount)
    await refreshState()
  }

  async function submitChallengeStart(body: { called_shot_value?: number; target_team_id?: number }) {
    if (!token || !selectedChallenge) return
    await api.challengeStart(token, selectedChallenge.id, body)
    await refreshState()
  }

  async function submitChallengeResult(achievedValue?: number) {
    if (!token || !selectedChallenge) return
    await api.challengeSubmitResult(token, selectedChallenge.id, achievedValue)
    await refreshState()
    await refreshAttempts()
  }

  return (
    <div className="h-screen w-screen flex flex-col landscape:flex-row bg-slate-900 text-white overflow-hidden">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2.5 bg-slate-800/90 landscape:flex-col landscape:items-start landscape:w-64 landscape:h-full landscape:overflow-y-auto shrink-0 z-10">
        <div className="flex items-center gap-2 flex-1 landscape:w-full">
          <span className="w-3.5 h-3.5 rounded-full shrink-0" style={{ backgroundColor: myTeam.color_hex }} />
          <h1 className="font-black text-lg truncate">{myTeam.name}</h1>
        </div>
        <div className="text-right landscape:text-left landscape:w-full">
          <p className="font-bold tabular-nums">{myTeam.chips_balance} 枚代幣</p>
        </div>
        <div className="w-full landscape:w-full">
          <GameClock phase={state.phase} />
        </div>
        <nav className="hidden landscape:flex flex-col gap-1 w-full mt-2">
          <TabButton tab="ranking" current={tab} setTab={setTab} label="排名" />
          <TabButton tab="challenges" current={tab} setTab={setTab} label="任務" />
          <TabButton tab="log" current={tab} setTab={setTab} label="紀錄" />
        </nav>
        <div className="hidden landscape:block w-full mt-3 flex-1 min-h-0 overflow-y-auto">
          <TabContent
            tab={tab}
            state={state}
            log={log}
            challenges={challenges}
            myAttempts={myAttempts}
            onSelectChallenge={setSelectedChallenge}
          />
        </div>
      </header>

      <main className="flex-1 min-h-0 min-w-0 relative">
        <MetroMap
          mapData={mapData}
          teams={state.ranking}
          challenges={challenges}
          gps={gps}
          onStationClick={setSelectedStation}
          onChallengeClick={setSelectedChallenge}
          meetingStationIds={myTeam.meeting_station_id ? [myTeam.meeting_station_id] : []}
        />
      </main>

      <nav className="flex landscape:hidden bg-slate-800/90 shrink-0">
        <TabButton tab="ranking" current={tab} setTab={setTab} label="排名" grow />
        <TabButton tab="challenges" current={tab} setTab={setTab} label="任務" grow />
        <TabButton tab="log" current={tab} setTab={setTab} label="紀錄" grow />
      </nav>
      <div className="landscape:hidden bg-slate-800/60 h-56 overflow-y-auto p-3 shrink-0">
        <TabContent
          tab={tab}
          state={state}
          log={log}
          challenges={challenges}
          myAttempts={myAttempts}
          onSelectChallenge={setSelectedChallenge}
        />
      </div>

      {selectedStation && (
        <ClaimSheet
          station={selectedStation}
          mapData={mapData}
          myTeamId={myTeam.id}
          teams={state.ranking}
          hasPendingRequest={!!pendingStationRequest}
          maxDepositPerVisit={maxDepositPerVisit}
          onClose={() => setSelectedStation(null)}
          onSubmit={submitClaim}
        />
      )}

      {selectedChallenge && (
        <ChallengeModal
          teaser={selectedChallenge}
          attempt={selectedAttempt}
          fullDetail={challengeDetail}
          teams={state.ranking}
          myTeamId={myTeam.id}
          hasPendingRequest={!!pendingChallengeRequest}
          onClose={() => setSelectedChallenge(null)}
          onStart={submitChallengeStart}
          onSubmitResult={submitChallengeResult}
        />
      )}
    </div>
  )
}

function TabButton({
  tab,
  current,
  setTab,
  label,
  grow,
}: {
  tab: Tab
  current: Tab
  setTab: (t: Tab) => void
  label: string
  grow?: boolean
}) {
  return (
    <button
      onClick={() => setTab(tab)}
      className={`py-2.5 text-sm font-bold ${grow ? 'flex-1' : 'w-full text-left px-3 rounded-lg'} ${
        current === tab ? 'text-white bg-white/10' : 'text-white/50'
      }`}
    >
      {label}
    </button>
  )
}

function TabContent({
  tab,
  state,
  log,
  challenges,
  myAttempts,
  onSelectChallenge,
}: {
  tab: Tab
  state: TeamState
  log: ActionLogEntry[]
  challenges: ChallengeTeaser[]
  myAttempts: ChallengeAttempt[]
  onSelectChallenge: (c: ChallengeTeaser) => void
}) {
  if (tab === 'ranking') return <RankingBoard ranking={state.ranking} highlightTeamId={state.team.id} />
  if (tab === 'log') return <ActionLogList entries={log} />
  const attemptByChallenge = new Map(myAttempts.map((a) => [a.challenge_id, a]))
  return (
    <div className="flex flex-col gap-1.5">
      {challenges.length === 0 && <p className="text-white/40 text-sm py-4 text-center">目前沒有可用任務</p>}
      {challenges.map((c) => {
        const attempt = attemptByChallenge.get(c.id)
        return (
          <button
            key={c.id}
            onClick={() => onSelectChallenge(c)}
            className="text-left bg-white/5 rounded-lg px-3 py-2 text-sm flex justify-between items-center"
          >
            <span className="font-medium">{c.name}</span>
            <StatusBadge attempt={attempt} />
          </button>
        )
      })}
    </div>
  )
}

function StatusBadge({ attempt }: { attempt: ChallengeAttempt | undefined }) {
  if (!attempt) return <span className="text-white/40 text-xs">尚未嘗試</span>
  const labels: Record<string, string> = {
    in_progress: '進行中',
    pending_result: '待判定',
    success: '成功',
    failed: '失敗',
    pending_start_approval: '待核准',
  }
  const colors: Record<string, string> = {
    success: 'text-emerald-400',
    failed: 'text-rose-400',
    in_progress: 'text-amber-300',
    pending_result: 'text-amber-300',
  }
  return <span className={`text-xs ${colors[attempt.status] || 'text-white/50'}`}>{labels[attempt.status]}</span>
}
