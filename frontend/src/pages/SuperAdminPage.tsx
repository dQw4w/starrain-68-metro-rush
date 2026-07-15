import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import ActionLogList from '../components/ActionLogList'
import RankingBoard from '../components/RankingBoard'
import { useWebSocket, type WsEvent } from '../hooks/useWebSocket'
import { clearAdminSession, loadAdminSession } from '../lib/adminSession'
import type { ActionLogEntry, Challenge, GameConfig, TeamAdminView } from '../types'

type Tab = 'overview' | 'teams' | 'config' | 'challenges' | 'log'

export default function SuperAdminPage() {
  const navigate = useNavigate()
  const session = loadAdminSession()
  const token = session?.token || ''

  const [tab, setTab] = useState<Tab>('overview')
  const [teams, setTeams] = useState<TeamAdminView[]>([])
  const [config, setConfig] = useState<GameConfig | null>(null)
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const [log, setLog] = useState<ActionLogEntry[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!session || !session.is_super) navigate('/admin/login')
  }, [session, navigate])

  const refresh = useCallback(async () => {
    if (!token) return
    const [t, c, ch] = await Promise.all([api.listTeams(token), api.getConfig(token), api.listAllChallenges(token)])
    setTeams(t)
    setConfig(c)
    setChallenges(ch)
    api.globalLog(token).then(setLog).catch(() => {})
  }, [token])

  useEffect(() => {
    refresh()
  }, [refresh])

  const getTicket = useCallback(async () => {
    if (!token) throw new Error('not logged in')
    return (await api.adminWsTicket(token)).ticket
  }, [token])
  const handleWsEvent = useCallback(
    (ev: WsEvent) => {
      if (['__connected__', 'map_update', 'ranking_update', 'team_update', 'challenge_pool', 'config_update'].includes(ev.type)) {
        refresh()
      }
    },
    [refresh]
  )
  useWebSocket(getTicket, handleWsEvent)

  function logout() {
    clearAdminSession()
    navigate('/admin/login')
  }

  const ranking = [...teams].sort((a, b) => b.stations_owned - a.stations_owned || b.chips_balance - a.chips_balance)

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col">
      <header className="flex items-center gap-3 px-4 py-3 bg-slate-800">
        <h1 className="font-black text-lg flex-1">Metro Rush｜總管理員</h1>
        <button onClick={logout} className="text-white/50 text-sm">
          登出
        </button>
      </header>

      <nav className="flex bg-slate-800/60 overflow-x-auto">
        {(['overview', 'teams', 'config', 'challenges', 'log'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-bold whitespace-nowrap ${tab === t ? 'text-white bg-white/10' : 'text-white/50'}`}
          >
            {{ overview: '總覽', teams: '隊伍', config: '賽事設定', challenges: '任務管理', log: '全域紀錄' }[t]}
          </button>
        ))}
      </nav>

      {error && <div className="bg-rose-600 text-white text-sm p-2 text-center">{error}</div>}

      <main className="flex-1 p-4 overflow-y-auto">
        {tab === 'overview' && <RankingBoard ranking={ranking} />}

        {tab === 'teams' && (
          <TeamsTab
            teams={teams}
            token={token}
            onChanged={refresh}
            onError={(m) => setError(m)}
            configLocked={config?.locked ?? false}
          />
        )}

        {tab === 'config' && config && (
          <ConfigTab config={config} onSave={async (patch) => {
            try {
              const updated = await api.updateConfig(token, patch)
              setConfig(updated)
            } catch (e: any) {
              setError(e.message || '設定更新失敗')
            }
          }} />
        )}

        {tab === 'challenges' && (
          <ChallengesTab
            challenges={challenges}
            token={token}
            onChanged={refresh}
            onError={(m) => setError(m)}
          />
        )}

        {tab === 'log' && <ActionLogList entries={log} />}
      </main>
    </div>
  )
}

function TeamsTab({
  teams,
  token,
  onChanged,
  onError,
  configLocked,
}: {
  teams: TeamAdminView[]
  token: string
  onChanged: () => void
  onError: (m: string) => void
  configLocked: boolean
}) {
  const [name, setName] = useState('')
  const [color, setColor] = useState('#3B82F6')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)

  async function createTeam(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.createTeam(token, { name, color_hex: color, admin_pin: pin })
      setName('')
      setPin('')
      onChanged()
    } catch (e: any) {
      onError(e.message || '新增隊伍失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-xl">
      <div className="flex flex-col gap-2">
        {teams.map((t) => {
          const playerUrl = `${window.location.origin}/team/${t.share_token}`
          return (
          <div key={t.id} className="bg-white/5 rounded-xl p-3 flex flex-col gap-2">
            <div className="flex items-center gap-3">
              <span className="w-3.5 h-3.5 rounded-full shrink-0" style={{ backgroundColor: t.color_hex }} />
              <div className="flex-1">
                <p className="font-bold">{t.name}</p>
                <p className="text-xs text-white/50">
                  {t.stations_owned} 站 · {t.chips_balance} 枚
                </p>
              </div>
              <Link to={`/admin/team/${t.id}`} className="bg-blue-600 rounded-lg px-3 py-1.5 text-sm font-bold">
                進入審核
              </Link>
            </div>
            <div className="flex items-center gap-2 bg-black/20 rounded-lg px-2 py-1.5">
              <a href={playerUrl} target="_blank" rel="noreferrer" className="flex-1 text-xs text-blue-300 truncate">
                {playerUrl}
              </a>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(playerUrl)}
                className="text-xs bg-white/10 rounded px-2 py-1 shrink-0"
              >
                複製連結
              </button>
            </div>
          </div>
          )
        })}
      </div>

      {!configLocked && (
        <form onSubmit={createTeam} className="bg-white/5 rounded-xl p-3 flex flex-col gap-2">
          <p className="font-bold text-sm">新增隊伍</p>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="隊名" required className="bg-white/10 rounded-lg px-3 py-2 text-sm" />
          <div className="flex gap-2">
            <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-10 w-14 bg-white/10 rounded-lg" />
            <input
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="管理員 PIN 碼"
              required
              className="flex-1 bg-white/10 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <button disabled={busy} className="bg-emerald-600 disabled:opacity-40 rounded-lg py-2 font-bold text-sm">
            新增
          </button>
        </form>
      )}
      {configLocked && <p className="text-white/40 text-sm">遊戲已開始，無法再新增隊伍。</p>}
    </div>
  )
}

function ConfigTab({ config, onSave }: { config: GameConfig; onSave: (patch: Partial<GameConfig>) => Promise<void> }) {
  const [form, setForm] = useState(config)
  const [busy, setBusy] = useState(false)

  useEffect(() => setForm(config), [config])

  function field<K extends keyof GameConfig>(key: K, label: string, type = 'text') {
    return (
      <label className="text-sm flex flex-col gap-1">
        {label}
        <input
          type={type}
          value={String(form[key] ?? '')}
          disabled={config.locked && !['override_status'].includes(key as string)}
          onChange={(e) => setForm({ ...form, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
          className="bg-white/10 rounded-lg px-3 py-2 disabled:opacity-40"
        />
      </label>
    )
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        try {
          await onSave(form)
        } finally {
          setBusy(false)
        }
      }}
      className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl"
    >
      {config.locked && (
        <p className="sm:col-span-2 text-amber-300 text-sm bg-amber-500/10 rounded-lg p-2">
          遊戲已開始：僅能調整「緊急狀態」欄位（暫停 / 強制結束）。
        </p>
      )}
      {field('team_count', '隊伍數', 'number')}
      {field('game_date', '比賽日期', 'date')}
      {field('start_time', '開始時間', 'time')}
      {field('end_time', '結束時間', 'time')}
      {field('lunch_start', '午休開始', 'time')}
      {field('lunch_end', '午休結束', 'time')}
      {field('starting_chips', '起始代幣', 'number')}
      {field('max_deposit_per_visit', '單次最高投入', 'number')}
      {field('fail_bonus_step_pct', '失敗加成 %/隊', 'number')}
      {field('challenge_pool_initial', '任務池初始數', 'number')}
      {field('challenge_pool_refill', '任務池補充數', 'number')}
      {field('challenge_pool_max', '任務池上限', 'number')}
      <label className="text-sm flex flex-col gap-1">
        緊急狀態
        <select
          value={form.override_status}
          onChange={(e) => setForm({ ...form, override_status: e.target.value as GameConfig['override_status'] })}
          className="bg-white/10 rounded-lg px-3 py-2"
        >
          <option value="auto">正常（依時間表自動運作）</option>
          <option value="paused">暫停遊戲</option>
          <option value="force_ended">強制結束</option>
        </select>
      </label>
      <button disabled={busy} className="sm:col-span-2 bg-blue-600 disabled:opacity-40 rounded-lg py-2.5 font-bold">
        儲存設定
      </button>
    </form>
  )
}

function ChallengesTab({
  challenges,
  token,
  onChanged,
  onError,
}: {
  challenges: Challenge[]
  token: string
  onChanged: () => void
  onError: (m: string) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [type, setType] = useState<Challenge['type']>('fixed')
  const [locationName, setLocationName] = useState('')
  const [lat, setLat] = useState('')
  const [lng, setLng] = useState('')
  const [rewardValue, setRewardValue] = useState('')
  const [busy, setBusy] = useState(false)

  const rewardConfig = () => {
    if (type === 'fixed') return { chips: Number(rewardValue) }
    if (type === 'variable') return { chips_per_unit: Number(rewardValue), unit_label: '單位' }
    if (type === 'steal') return { steal_pct: Number(rewardValue) }
    return { multiplier_pct: Number(rewardValue) }
  }

  async function createChallenge(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.createChallenge(token, {
        name,
        description,
        type,
        reward_config: rewardConfig(),
        location_name: locationName || undefined,
        lat: lat ? Number(lat) : undefined,
        lng: lng ? Number(lng) : undefined,
        pool_state: 'queued',
      })
      setName('')
      setDescription('')
      setLocationName('')
      setLat('')
      setLng('')
      setRewardValue('')
      onChanged()
    } catch (e: any) {
      onError(e.message || '新增任務失敗')
    } finally {
      setBusy(false)
    }
  }

  async function setPoolState(id: number, pool_state: Challenge['pool_state']) {
    try {
      await api.updateChallenge(token, id, { pool_state })
      onChanged()
    } catch (e: any) {
      onError(e.message || '更新失敗')
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-xl">
      <button
        onClick={async () => {
          try {
            await api.activatePool(token)
            onChanged()
          } catch (e: any) {
            onError(e.message || '啟動任務池失敗')
          }
        }}
        className="bg-purple-600 rounded-lg py-2 font-bold text-sm self-start px-4"
      >
        啟動初始任務池
      </button>

      <div className="flex flex-col gap-2">
        {challenges.map((c) => (
          <div key={c.id} className="bg-white/5 rounded-xl p-3">
            <div className="flex justify-between items-baseline">
              <p className="font-bold">{c.name}</p>
              <span className="text-xs text-white/50">{c.pool_state}</span>
            </div>
            <p className="text-xs text-white/50">{c.type}</p>
            <div className="flex gap-2 mt-2">
              {c.pool_state !== 'active' && (
                <button onClick={() => setPoolState(c.id, 'active')} className="bg-emerald-600 rounded-lg px-3 py-1 text-xs font-bold">
                  上架
                </button>
              )}
              {c.pool_state !== 'retired' && (
                <button onClick={() => setPoolState(c.id, 'retired')} className="bg-rose-600 rounded-lg px-3 py-1 text-xs font-bold">
                  下架
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={createChallenge} className="bg-white/5 rounded-xl p-3 flex flex-col gap-2">
        <p className="font-bold text-sm">新增任務</p>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="任務名稱" required className="bg-white/10 rounded-lg px-3 py-2 text-sm" />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="任務敘述（核准開始後才會顯示給隊伍）"
          required
          className="bg-white/10 rounded-lg px-3 py-2 text-sm"
        />
        <select value={type} onChange={(e) => setType(e.target.value as Challenge['type'])} className="bg-white/10 rounded-lg px-3 py-2 text-sm">
          <option value="fixed">固定獎勵</option>
          <option value="variable">Call your shot</option>
          <option value="steal">偷竊</option>
          <option value="multiplier">倍率</option>
        </select>
        <input
          value={rewardValue}
          onChange={(e) => setRewardValue(e.target.value)}
          placeholder={type === 'fixed' ? '固定代幣數' : type === 'variable' ? '每單位代幣數' : type === 'steal' ? '偷竊百分比' : '倍率百分比'}
          type="number"
          required
          className="bg-white/10 rounded-lg px-3 py-2 text-sm"
        />
        <input value={locationName} onChange={(e) => setLocationName(e.target.value)} placeholder="地點名稱" className="bg-white/10 rounded-lg px-3 py-2 text-sm" />
        <div className="flex gap-2">
          <input value={lat} onChange={(e) => setLat(e.target.value)} placeholder="緯度" className="flex-1 bg-white/10 rounded-lg px-3 py-2 text-sm" />
          <input value={lng} onChange={(e) => setLng(e.target.value)} placeholder="經度" className="flex-1 bg-white/10 rounded-lg px-3 py-2 text-sm" />
        </div>
        <button disabled={busy} className="bg-emerald-600 disabled:opacity-40 rounded-lg py-2 font-bold text-sm">
          新增任務（加入待命池）
        </button>
      </form>
    </div>
  )
}
