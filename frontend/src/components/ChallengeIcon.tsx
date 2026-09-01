import type { ChallengeTeaser } from '../types'

/** Only location, type, and reward *value* are ever revealed on the map — the
 * icon's shape encodes type, its label encodes value, matching the game's
 * rule that name/description stay hidden until a team takes the challenge on. */
export const CHALLENGE_TYPE_LABELS: Record<ChallengeTeaser['type'], string> = {
  fixed: '固定獎勵',
  variable: 'Call your shot',
  steal: '偷竊任務',
  multiplier: '倍率任務',
}

interface IconStyle {
  shape: 'circle' | 'square' | 'diamond'
  bg: string
  fg: string
}

const STYLES: Record<ChallengeTeaser['type'], IconStyle> = {
  fixed: { shape: 'circle', bg: '#7C3AED', fg: '#ffffff' },
  multiplier: { shape: 'square', bg: '#0EA5E9', fg: '#ffffff' },
  variable: { shape: 'square', bg: '#F59E0B', fg: '#111827' },
  steal: { shape: 'diamond', bg: '#DC2626', fg: '#ffffff' },
}

export function challengeIconLabel(ch: ChallengeTeaser): string {
  const rc: Record<string, any> = ch.reward_config || {}
  if (ch.type === 'fixed') return String(rc.chips ?? '')
  if (ch.type === 'multiplier') return `×${rc.multiplier_pct ?? ''}%`
  if (ch.type === 'variable') return '?'
  if (ch.type === 'steal') return `${rc.steal_pct ?? ''}%`
  return ''
}

function fontSizeFor(label: string, size: number): number {
  if (label === '?') return Math.round(size * 0.55)
  if (label.length > 3) return Math.round(size * 0.32)
  return Math.round(size * 0.38)
}

/** How many prior teams have failed a challenge translates to a % reward bonus for whoever attempts it next. */
export function failBonusPct(ch: ChallengeTeaser, failBonusStepPct: number): number {
  return ch.prior_fail_count * failBonusStepPct
}

/** Raw HTML for the fail-bonus corner badge — sits outside any shape rotation so it always reads upright. */
function bonusBadgeHtml(size: number): string {
  const badgeSize = Math.max(12, Math.round(size * 0.55))
  return (
    `<span style="position:absolute;top:-4px;right:-4px;width:${badgeSize}px;height:${badgeSize}px;` +
    `border-radius:50%;background:#DC2626;border:1.5px solid #fff;display:flex;align-items:center;` +
    `justify-content:center;font-size:${Math.round(badgeSize * 0.68)}px;line-height:1;` +
    `box-shadow:0 1px 3px rgba(0,0,0,.5)">🔥</span>`
  )
}

/** Raw HTML for a Leaflet `L.divIcon` — used for the map pin (can't render React inside Leaflet's icon). */
export function challengeIconHtml(ch: ChallengeTeaser, size = 28): string {
  const s = STYLES[ch.type]
  const label = challengeIconLabel(ch)
  const fontSize = fontSizeFor(label, size)
  const shapeRadius = s.shape === 'circle' ? '50%' : s.shape === 'diamond' ? '4px' : '6px'
  const outerTransform = s.shape === 'diamond' ? 'transform:rotate(45deg);' : ''
  const innerTransform = s.shape === 'diamond' ? 'transform:rotate(-45deg);' : ''
  const badge = ch.prior_fail_count > 0 ? bonusBadgeHtml(size) : ''
  return (
    `<div style="position:relative;width:${size}px;height:${size}px;">` +
    `<div style="width:100%;height:100%;border-radius:${shapeRadius};${outerTransform}` +
    `background:${s.bg};border:2px solid #fff;display:flex;align-items:center;justify-content:center;` +
    `box-shadow:0 1px 4px rgba(0,0,0,.45)">` +
    `<span style="${innerTransform}color:${s.fg};font-weight:800;font-size:${fontSize}px;font-family:sans-serif;line-height:1;">` +
    `${label}</span></div>${badge}</div>`
  )
}

/** React version of the same badge, for use in list rows / modal headers. */
export function ChallengeIconBadge({ challenge, size = 28 }: { challenge: ChallengeTeaser; size?: number }) {
  const s = STYLES[challenge.type]
  const label = challengeIconLabel(challenge)
  const fontSize = fontSizeFor(label, size)
  const borderRadius = s.shape === 'circle' ? '50%' : s.shape === 'diamond' ? '4px' : '6px'
  const badgeSize = Math.max(12, Math.round(size * 0.55))
  return (
    <span style={{ position: 'relative', width: size, height: size, display: 'inline-flex', flexShrink: 0 }}>
      <span
        style={{
          width: size,
          height: size,
          borderRadius,
          transform: s.shape === 'diamond' ? 'rotate(45deg)' : undefined,
          background: s.bg,
          border: '2px solid white',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,.3)',
        }}
      >
        <span
          style={{
            transform: s.shape === 'diamond' ? 'rotate(-45deg)' : undefined,
            color: s.fg,
            fontWeight: 800,
            fontSize,
            lineHeight: 1,
          }}
        >
          {label}
        </span>
      </span>
      {challenge.prior_fail_count > 0 && (
        <span
          title="已有隊伍失敗過此任務，本次挑戰有加成"
          style={{
            position: 'absolute',
            top: -4,
            right: -4,
            width: badgeSize,
            height: badgeSize,
            borderRadius: '50%',
            background: '#DC2626',
            border: '1.5px solid white',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: Math.round(badgeSize * 0.68),
            lineHeight: 1,
            boxShadow: '0 1px 3px rgba(0,0,0,.5)',
          }}
        >
          🔥
        </span>
      )}
    </span>
  )
}
