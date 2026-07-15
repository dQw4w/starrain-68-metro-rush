import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { saveAdminSession } from '../lib/adminSession'

export default function AdminLoginPage() {
  const navigate = useNavigate()
  const [role, setRole] = useState<'team' | 'super'>('team')
  const [teams, setTeams] = useState<{ id: number; name: string; color_hex: string }[] | null>(null)
  const [teamsError, setTeamsError] = useState('')
  const [teamId, setTeamId] = useState<number | ''>('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .listTeamsPublic()
      .then((t) => {
        setTeams(t)
        setTeamsError('')
      })
      .catch((e: any) => setTeamsError(e.message || '無法載入隊伍清單'))
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const session = await api.login({
        role,
        team_id: role === 'team' ? (teamId === '' ? undefined : Number(teamId)) : undefined,
        pin,
      })
      saveAdminSession(session)
      navigate(session.is_super ? '/superadmin' : `/admin/team/${session.team_id}`)
    } catch (e: any) {
      setError(e.message || '登入失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="bg-slate-800 rounded-2xl p-6 w-full max-w-sm flex flex-col gap-4">
        <h1 className="text-2xl font-black text-center">Metro Rush 管理登入</h1>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setRole('team')}
            className={`flex-1 py-2 rounded-lg font-bold ${role === 'team' ? 'bg-blue-600' : 'bg-white/10'}`}
          >
            隨隊管理員
          </button>
          <button
            type="button"
            onClick={() => setRole('super')}
            className={`flex-1 py-2 rounded-lg font-bold ${role === 'super' ? 'bg-blue-600' : 'bg-white/10'}`}
          >
            總管理員
          </button>
        </div>

        {role === 'team' && (
          <>
            <select
              value={teamId}
              onChange={(e) => setTeamId(e.target.value === '' ? '' : Number(e.target.value))}
              required
              className="bg-white/10 rounded-lg px-3 py-2.5"
            >
              <option value="">選擇隊伍</option>
              {(teams || []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            {teamsError && <p className="text-rose-400 text-sm">隊伍清單載入失敗：{teamsError}</p>}
            {!teamsError && teams && teams.length === 0 && (
              <p className="text-amber-300 text-sm">
                目前尚未建立任何隊伍，請先以「總管理員」登入並在「隊伍」頁籤新增隊伍。
              </p>
            )}
          </>
        )}

        <input
          type="password"
          inputMode="numeric"
          placeholder="PIN 碼"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          required
          className="bg-white/10 rounded-lg px-3 py-2.5"
        />

        {error && <p className="text-rose-400 text-sm">{error}</p>}

        <button disabled={busy} type="submit" className="bg-emerald-600 disabled:opacity-40 font-bold rounded-lg py-2.5">
          登入
        </button>
      </form>
    </div>
  )
}
