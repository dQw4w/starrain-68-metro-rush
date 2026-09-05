import { useEffect, useState } from 'react'
import { CHALLENGE_TYPE_LABELS, ChallengeIconBadge, failBonusPct } from './ChallengeIcon'
import type { Challenge, ChallengeAttempt, ChallengeTeaser, TeamPublic } from '../types'

const TYPE_LABELS: Record<string, string> = {
  ...CHALLENGE_TYPE_LABELS,
  variable: '猜拳式獎勵（核准開始後才喊出目標數量）',
}

/** Positive-integer-only text (mini task counts are never fractional or negative). Empty string is allowed while typing/clearing. */
const isPositiveIntInput = (v: string) => v === '' || /^[1-9]\d*$/.test(v)

interface Props {
  teaser: ChallengeTeaser
  attempt: ChallengeAttempt | undefined
  fullDetail: Challenge | null
  teams: TeamPublic[]
  myTeamId: number
  hasPendingRequest: boolean
  /** % reward bonus per prior team that failed this challenge. */
  failBonusStepPct: number
  onClose: () => void
  onStart: (body: { target_team_id?: number }) => Promise<void>
  /** Call-your-shot (variable) challenges only — submitted once in_progress, after the team has seen the full task description. */
  onSubmitShot: (calledShotValue: number) => Promise<void>
}

export default function ChallengeModal({
  teaser,
  attempt,
  fullDetail,
  teams,
  myTeamId,
  hasPendingRequest,
  failBonusStepPct,
  onClose,
  onStart,
  onSubmitShot,
}: Props) {
  const [calledShot, setCalledShot] = useState('')
  const [targetTeamId, setTargetTeamId] = useState<number | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
  }, [teaser.id])

  const otherTeams = teams.filter((t) => t.id !== myTeamId && t.active)
  const chipsPerUnit = Number(teaser.reward_config.chips_per_unit) || 0
  const unitLabel = teaser.reward_config.unit_label || 'mini task'
  const calledShotValue = /^[1-9]\d*$/.test(calledShot) ? Number(calledShot) : null
  const bonusPct = failBonusPct(teaser, failBonusStepPct)

  async function handleStart() {
    setBusy(true)
    setError('')
    try {
      await onStart({
        target_team_id: targetTeamId === '' ? undefined : Number(targetTeamId),
      })
    } catch (e: any) {
      setError(e.message || '操作失敗')
    } finally {
      setBusy(false)
    }
  }

  async function handleSubmitShot() {
    if (calledShotValue === null) return
    setBusy(true)
    setError('')
    try {
      await onSubmitShot(calledShotValue)
    } catch (e: any) {
      setError(e.message || '送出失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[2000] flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" onClick={onClose}>
      <div
        className="bg-slate-800 text-white rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[85vh] overflow-y-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-start gap-3 mb-2">
          <div className="flex items-center gap-3">
            <ChallengeIconBadge challenge={teaser} size={36} />
            <div>
              <h2 className="text-xl font-bold">{teaser.name}</h2>
              {fullDetail && fullDetail.inner_title && (
                <p className="text-sm text-amber-300 font-medium">{fullDetail.inner_title}</p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-white/50 text-2xl leading-none shrink-0">
            &times;
          </button>
        </div>
        <p className="text-sm text-purple-300 mb-1">{TYPE_LABELS[teaser.type]}</p>
        {teaser.location_name && <p className="text-sm text-white/60 mb-3">📍 {teaser.location_name}</p>}
        {teaser.image_url && (
          <img src={teaser.image_url} alt="" className="w-full max-h-56 object-cover rounded-xl mb-3" />
        )}
        {teaser.prior_fail_count > 0 && (
          <p className="text-sm font-bold text-rose-400 bg-rose-500/10 rounded-lg px-3 py-2 mb-3">
            🔥 已有 {teaser.prior_fail_count} 隊挑戰失敗，本次挑戰獎勵加成 +{bonusPct}%
          </p>
        )}
        <RewardSummary teaser={teaser} bonusPct={bonusPct} />

        {error && <p className="text-rose-400 text-sm mt-3">{error}</p>}

        {!attempt && !hasPendingRequest && (
          <div className="mt-4 flex flex-col gap-3">
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
              挑戰任務（需管理員核准）
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

            {teaser.type === 'variable' && attempt.called_shot_value == null ? (
              <label className="text-sm">
                喊出目標數量（必填）—— 欲挑戰的「{unitLabel}」數量（非代幣數量），須為正整數
                <input
                  type="number"
                  inputMode="numeric"
                  min={1}
                  step={1}
                  value={calledShot}
                  onChange={(e) => {
                    if (isPositiveIntInput(e.target.value)) setCalledShot(e.target.value)
                  }}
                  className="mt-1 w-full bg-white/10 rounded-lg px-3 py-2"
                />
                {calledShotValue != null && chipsPerUnit > 0 && (
                  <p className="mt-1 text-emerald-400 text-xs">
                    成功可獲得 {calledShotValue} × {chipsPerUnit} = {calledShotValue * chipsPerUnit} 枚代幣
                    {bonusPct > 0 && `（含 +${bonusPct}% 加成後為 ${Math.round(calledShotValue * chipsPerUnit * (1 + bonusPct / 100))}）`}
                  </p>
                )}
                <button
                  disabled={busy || calledShotValue === null}
                  onClick={handleSubmitShot}
                  className="mt-2 w-full bg-purple-600 disabled:opacity-40 font-bold rounded-xl py-3"
                >
                  送出
                </button>
              </label>
            ) : (
              <p className="text-amber-300 font-bold text-center py-2">
                {teaser.type === 'variable' && attempt.called_shot_value != null
                  ? `🚀 已喊出目標數量：${attempt.called_shot_value}，請等待隨隊管理員判定成功或失敗`
                  : '🚀 任務進行中，請等待隨隊管理員判定成功或失敗'}
              </p>
            )}
          </div>
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

function RewardSummary({ teaser, bonusPct }: { teaser: ChallengeTeaser; bonusPct: number }) {
  const rc = teaser.reward_config
  const bonusNote = (base: number) => (bonusPct > 0 ? `（含 +${bonusPct}% 加成後為 ${Math.round(base * (1 + bonusPct / 100))}）` : '')
  if (teaser.type === 'fixed') return <p className="text-sm">獎勵：{rc.chips} 枚代幣{bonusNote(Number(rc.chips) || 0)}</p>
  if (teaser.type === 'variable')
    return (
      <p className="text-sm">
        獎勵：每完成 1 個「{rc.unit_label || 'mini task'}」可得 {rc.chips_per_unit} 枚代幣{bonusNote(Number(rc.chips_per_unit) || 0)}
        （需達成喊出的數量才算成功；獲得代幣數 = 完成數量 × 每單位代幣數）
      </p>
    )
  if (teaser.type === 'steal') return <p className="text-sm">獎勵：偷取目標隊伍 {rc.steal_pct}% 的代幣{bonusNote(Number(rc.steal_pct) || 0)}</p>
  if (teaser.type === 'multiplier') return <p className="text-sm">獎勵：己隊代幣 +{rc.multiplier_pct}%{bonusNote(Number(rc.multiplier_pct) || 0)}</p>
  return null
}
