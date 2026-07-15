import { useCallback, useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { api } from '../api'
import type { Line, LineStationOrderEntry } from '../types'

const STORAGE_KEY = 'metro_rush_waypoint_progress'

type Point = [number, number]

interface Pair {
  from: LineStationOrderEntry
  to: LineStationOrderEntry
}

function pairKey(lineCode: string, from: string, to: string) {
  return `${lineCode}::${from}::${to}`
}

function loadProgress(): Record<string, Point[]> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveProgress(p: Record<string, Point[]>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
}

export default function LineWaypointEditor({ token }: { token: string }) {
  const [lines, setLines] = useState<Line[]>([])
  const [lineOrder, setLineOrder] = useState<Record<string, LineStationOrderEntry[]>>({})
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null)
  const [selectedPair, setSelectedPair] = useState<Pair | null>(null)
  const [progress, setProgress] = useState<Record<string, Point[]>>(() => loadProgress())
  const [error, setError] = useState('')

  useEffect(() => {
    api.getMap().then((d) => setLines(d.lines)).catch((e) => setError(e.message))
    api.lineStationOrder(token).then(setLineOrder).catch((e) => setError(e.message))
  }, [token])

  useEffect(() => {
    saveProgress(progress)
  }, [progress])

  const selectedLine = lines.find((l) => l.id === selectedLineId) || null

  const pairs: Pair[] = useMemo(() => {
    if (!selectedLineId) return []
    const stations = lineOrder[String(selectedLineId)] || []
    const out: Pair[] = []
    for (let i = 0; i < stations.length - 1; i++) {
      out.push({ from: stations[i], to: stations[i + 1] })
    }
    return out
  }, [selectedLineId, lineOrder])

  const currentKey = selectedLine && selectedPair ? pairKey(selectedLine.code, selectedPair.from.name_zh, selectedPair.to.name_zh) : null
  const currentPoints = currentKey ? progress[currentKey] || [] : []

  function addPoint(pt: Point) {
    if (!currentKey) return
    setProgress((prev) => ({ ...prev, [currentKey]: [...(prev[currentKey] || []), pt] }))
  }

  function undoPoint() {
    if (!currentKey) return
    setProgress((prev) => ({ ...prev, [currentKey]: (prev[currentKey] || []).slice(0, -1) }))
  }

  function clearPair(key: string) {
    setProgress((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  function clearAll() {
    if (!window.confirm('確定要清除所有已記錄的路徑點嗎？此動作無法復原。')) return
    setProgress({})
  }

  const editedKeys = Object.keys(progress).filter((k) => progress[k]?.length > 0)

  const codeOutput = useMemo(() => {
    if (editedKeys.length === 0) return ''
    const lines = editedKeys.map((key) => {
      const [lineCode, from, to] = key.split('::')
      const pts = progress[key]
      const ptsStr = pts.map(([lat, lng]) => `(${lat.toFixed(6)}, ${lng.toFixed(6)})`).join(', ')
      return `    ("${lineCode}", "${from}", "${to}"): [${ptsStr}],`
    })
    return lines.join('\n')
  }, [editedKeys, progress])

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-rose-400 text-sm">{error}</p>}

      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={selectedLineId ?? ''}
          onChange={(e) => {
            setSelectedLineId(e.target.value ? Number(e.target.value) : null)
            setSelectedPair(null)
          }}
          className="bg-white/10 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">選擇路線</option>
          {lines.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name_zh} ({l.code})
            </option>
          ))}
        </select>
        {editedKeys.length > 0 && <span className="text-xs text-white/50">已記錄 {editedKeys.length} 段路徑，尚未輸出</span>}
      </div>

      {selectedLine && (
        <div className="flex flex-wrap gap-1.5">
          {pairs.map((p) => {
            const key = pairKey(selectedLine.code, p.from.name_zh, p.to.name_zh)
            const count = progress[key]?.length || 0
            const active = selectedPair && selectedPair.from.station_id === p.from.station_id && selectedPair.to.station_id === p.to.station_id
            return (
              <button
                key={key}
                onClick={() => setSelectedPair(p)}
                className={`text-xs rounded-lg px-2.5 py-1.5 ${
                  active ? 'bg-blue-600' : count > 0 ? 'bg-emerald-700/60' : 'bg-white/10'
                }`}
              >
                {p.from.name_zh} → {p.to.name_zh}
                {count > 0 && <span className="ml-1 opacity-70">({count})</span>}
              </button>
            )
          })}
        </div>
      )}

      {selectedLine && selectedPair && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm font-bold">
              編輯中：{selectedPair.from.name_zh} → {selectedPair.to.name_zh}（點擊地圖依序新增路徑點）
            </p>
            <div className="flex gap-2">
              <button onClick={undoPoint} disabled={currentPoints.length === 0} className="text-xs bg-white/10 disabled:opacity-30 rounded-lg px-3 py-1.5">
                復原上一步
              </button>
              <button
                onClick={() => currentKey && clearPair(currentKey)}
                disabled={currentPoints.length === 0}
                className="text-xs bg-rose-700/60 disabled:opacity-30 rounded-lg px-3 py-1.5"
              >
                清除此路段
              </button>
            </div>
          </div>

          <div className="h-[60vh] rounded-xl overflow-hidden">
            <WaypointMap pair={selectedPair} points={currentPoints} onMapClick={addPoint} />
          </div>

          {currentPoints.length > 0 && (
            <div className="text-xs text-white/60 flex flex-col gap-0.5">
              {currentPoints.map((pt, i) => (
                <span key={i}>
                  {i + 1}. {pt[0].toFixed(6)}, {pt[1].toFixed(6)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {editedKeys.length > 0 && (
        <div className="bg-white/5 rounded-xl p-3 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="font-bold text-sm">輸出程式碼（貼到 seed_stations.py 的 _LINE_WAYPOINTS 中）</p>
            <div className="flex gap-2">
              <button
                onClick={() => navigator.clipboard.writeText(codeOutput)}
                className="text-xs bg-blue-600 rounded-lg px-3 py-1.5 font-bold"
              >
                複製到剪貼簿
              </button>
              <button onClick={clearAll} className="text-xs bg-white/10 rounded-lg px-3 py-1.5">
                清除全部進度
              </button>
            </div>
          </div>
          <textarea
            readOnly
            value={codeOutput}
            rows={Math.min(20, editedKeys.length + 1)}
            className="w-full bg-black/40 text-emerald-300 font-mono text-xs rounded-lg p-3"
            onFocus={(e) => e.target.select()}
          />
        </div>
      )}
    </div>
  )
}

function WaypointMap({ pair, points, onMapClick }: { pair: Pair; points: Point[]; onMapClick: (pt: Point) => void }) {
  const fullPath: Point[] = [[pair.from.lat, pair.from.lng], ...points, [pair.to.lat, pair.to.lng]]
  return (
    <MapContainer center={[pair.from.lat, pair.from.lng]} zoom={16} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitToPair pair={pair} />
      <ClickCapture onClick={onMapClick} />
      <Polyline positions={fullPath} pathOptions={{ color: '#A78BFA', weight: 3, dashArray: '6 6' }} />
      <CircleMarker center={[pair.from.lat, pair.from.lng]} radius={9} pathOptions={{ color: '#111827', weight: 2, fillColor: '#22C55E', fillOpacity: 1 }}>
        <Tooltip permanent direction="top">
          起：{pair.from.name_zh}
        </Tooltip>
      </CircleMarker>
      <CircleMarker center={[pair.to.lat, pair.to.lng]} radius={9} pathOptions={{ color: '#111827', weight: 2, fillColor: '#EF4444', fillOpacity: 1 }}>
        <Tooltip permanent direction="top">
          終：{pair.to.name_zh}
        </Tooltip>
      </CircleMarker>
      {points.map((pt, i) => (
        <CircleMarker key={i} center={pt} radius={5} pathOptions={{ color: '#111827', weight: 1.5, fillColor: '#A78BFA', fillOpacity: 1 }}>
          <Tooltip direction="top">#{i + 1}</Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}

function ClickCapture({ onClick }: { onClick: (pt: Point) => void }) {
  useMapEvents({
    click(e) {
      onClick([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}

function FitToPair({ pair }: { pair: Pair }) {
  const map = useMap()
  const boundsKey = `${pair.from.station_id}-${pair.to.station_id}`
  const fit = useCallback(() => {
    const pts: Point[] = [[pair.from.lat, pair.from.lng], [pair.to.lat, pair.to.lng]]
    map.fitBounds(pts, { padding: [60, 60] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundsKey])
  useEffect(() => {
    fit()
  }, [fit])
  return null
}
