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

/** Raw HTML for a Leaflet `L.divIcon` — used for the map pin (can't render React inside Leaflet's icon). */
export function challengeIconHtml(ch: ChallengeTeaser, size = 28): string {
  const s = STYLES[ch.type]
  const label = challengeIconLabel(ch)
  const fontSize = fontSizeFor(label, size)
  const shapeRadius = s.shape === 'circle' ? '50%' : s.shape === 'diamond' ? '4px' : '6px'
  const outerTransform = s.shape === 'diamond' ? 'transform:rotate(45deg);' : ''
  const innerTransform = s.shape === 'diamond' ? 'transform:rotate(-45deg);' : ''
  return (
    `<div style="width:${size}px;height:${size}px;border-radius:${shapeRadius};${outerTransform}` +
    `background:${s.bg};border:2px solid #fff;display:flex;align-items:center;justify-content:center;` +
    `box-shadow:0 1px 4px rgba(0,0,0,.45)">` +
    `<span style="${innerTransform}color:${s.fg};font-weight:800;font-size:${fontSize}px;font-family:sans-serif;line-height:1;">` +
    `${label}</span></div>`
  )
}

/** React version of the same badge, for use in list rows / modal headers. */
export function ChallengeIconBadge({ challenge, size = 28 }: { challenge: ChallengeTeaser; size?: number }) {
  const s = STYLES[challenge.type]
  const label = challengeIconLabel(challenge)
  const fontSize = fontSizeFor(label, size)
  const borderRadius = s.shape === 'circle' ? '50%' : s.shape === 'diamond' ? '4px' : '6px'
  return (
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
        flexShrink: 0,
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
  )
}
