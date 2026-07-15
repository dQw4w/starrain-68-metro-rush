import type { TeamPublic } from '../types'

export default function RankingBoard({ ranking, highlightTeamId }: { ranking: TeamPublic[]; highlightTeamId?: number }) {
  return (
    <div className="flex flex-col gap-1.5">
      {ranking.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            t.id === highlightTeamId ? 'bg-white/15 ring-1 ring-white/40' : 'bg-white/5'
          }`}
        >
          <span className="w-5 text-center font-bold text-white/70">#{t.rank}</span>
          <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: t.color_hex }} />
          <span className="flex-1 truncate font-medium text-white">{t.name}</span>
          <span className="text-white/80 tabular-nums">{t.stations_owned} 站</span>
          <span className="text-white/50 tabular-nums w-14 text-right">{t.chips_balance} 枚</span>
        </div>
      ))}
    </div>
  )
}
