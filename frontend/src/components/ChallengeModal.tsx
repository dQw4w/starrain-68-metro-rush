import { useEffect, useState } from 'react'
import type { Challenge, ChallengeAttempt, ChallengeTeaser, TeamPublic } from '../types'

const TYPE_LABELS: Record<string, string> = {
  fixed: '固定獎勵',
  variable: '猜拳式獎勵（需先喊出目標數量）',
  steal: '偷竊任務',
  multiplier: '倍率任務',
}

interface Props {
  teaser: ChallengeTeaser
  attempt: ChallengeAttempt | undefined
  fullDetail: Challenge | null
  teams: TeamPublic[]
  myTeamId: number
  hasPendingRequest: boolean
  onClose: () => void
  onStart: (body: { called_shot_value?: number; target_team_id?: number }) => Promise<void>
  onSubmitResult: (achievedValue?: number) => Promise<void>
}

export default function ChallengeModal({
  teaser,
  attempt,
  fullDetail,
  teams,
  myTeamId,
  hasPendingRequest,
  onClose,
  onStart,
  onSubmitResult,
}: Props) {
  const [calledShot, setCalledShot] = useState('')
  const [targetTeamId, setTargetTeamId] = useState<number | ''>('')
  const [achieved, setAchieved] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
  }, [teaser.id])

  const otherTeams = teams.filter((t) => t.id !== myTeamId && t.active)

  async function handleStart() {
    setBusy(true)
    setError('')
    try {
      await onStart({
        called_shot_value: calledShot ? Number(calledShot) : undefined,
        target_team_id: targetTeamId === '' ? undefined : Number(targetTeamId),
      })
    } catch (e: any) {
      setError(e.message || '操作失敗')
    } finally {
      setBusy(false)
    }
  }

  async function handleSubmitResult() {
    setBusy(true)
    setError('')
    try {
      await onSubmitResult(achieved ? Number(achieved) : undefined)
    } catch (e: any) {
      setError(e.message || '操作失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" onClick={onClose}>
      <div
        className="bg-slate-800 text-white rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[85vh] overflow-y-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start gap-2 mb-2">
          <h2 className="text-xl font-bold">{teaser.name}</h2>
          <button onClick={onClose} className="text-white/50 text-2xl leading-none">
            &times;
          </button>
        </div>
        <p className="text-sm text-purple-300 mb-1">{TYPE_LABELS[teaser.type]}</p>
        {teaser.location_name && <p className="text-sm text-white/60 mb-3">📍 {teaser.location_name}</p>}
        <RewardSummary teaser={teaser} />

        {error && <p className="text-rose-400 text-sm mt-3">{error}</p>}

        {!attempt && !hasPendingRequest && (
          <div className="mt-4 flex flex-col gap-3">
            {teaser.type === 'variable' && (
              <label className="text-sm">
                喊出目標數量（Call your shot）
                <input
                  type="number"
                  value={calledShot}
                  onChange={(e) => setCalledShot(e.target.value)}
                  className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
                />
              </label>
            )}
            {teaser.type === 'steal' && (
              <label className="text-sm">
                選擇偷竊目標隊伍
                <select
                  value={targetTeamId}
                  onChange={(e) => setTargetTeamId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
                >
                  <option value="">請選擇</option>
                  {otherTeams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              disabled={busy || (teaser.type === 'steal' && targetTeamId === '')}
              onClick={handleStart}
              className="bg-purple-600 disabled:opacity-40 font-bold rounded-xl py-3"
            >
              開始任務（需管理員核准）
            </button>
          </div>
        )}

        {hasPendingRequest && !attempt && (
          <p className="mt-4 text-amber-300 font-medium">⏳ 等待隨隊管理員核准開始任務…</p>
        )}

        {attempt && attempt.status === 'in_progress' && (
          <div className="mt-4 flex flex-col gap-3">
            <div className="bg-white/5 rounded-xl p-3 text-sm whitespace-pre-wrap">
              {fullDetail ? fullDetail.description : '任務內容載入中…'}
            </div>
            {teaser.type === 'variable' && (
              <label className="text-sm">
                實際完成數量
                <input
                  type="number"
                  value={achieved}
                  onChange={(e) => setAchieved(e.target.value)}
                  className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
                />
              </label>
            )}
            <button disabled={busy} onClick={handleSubmitResult} className="bg-emerald-600 disabled:opacity-40 font-bold rounded-xl py-3">
              完成挑戰，送交管理員判定
            </button>
          </div>
        )}

        {attempt && attempt.status === 'pending_result' && (
          <p className="mt-4 text-amber-300 font-medium">⏳ 等待隨隊管理員判定結果…</p>
        )}

        {attempt && (attempt.status === 'success' || attempt.status === 'failed') && (
          <div className="mt-4">
            <p className={`font-bold text-lg ${attempt.status === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}>
              {attempt.status === 'success' ? '✅ 挑戰成功' : '❌ 挑戰失敗'}
            </p>
            {attempt.reward_amount != null && attempt.reward_amount > 0 && (
              <p className="text-white/80">獲得 {attempt.reward_amount} 枚代幣</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function RewardSummary({ teaser }: { teaser: ChallengeTeaser }) {
  const rc = teaser.reward_config
  if (teaser.type === 'fixed') return <p className="text-sm">獎勵：{rc.chips} 枚代幣</p>
  if (teaser.type === 'variable')
    return (
      <p className="text-sm">
        獎勵：每個{rc.unit_label || '單位'} {rc.chips_per_unit} 枚代幣（須達成喊出的數量才算成功）
      </p>
    )
  if (teaser.type === 'steal') return <p className="text-sm">獎勵：偷取目標隊伍 {rc.steal_pct}% 的代幣</p>
  if (teaser.type === 'multiplier') return <p className="text-sm">獎勵：己隊代幣 +{rc.multiplier_pct}%</p>
  return null
}
