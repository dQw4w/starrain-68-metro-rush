import L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { api } from '../api'
import type { MapData, Station } from '../types'

const STORAGE_KEY = 'metro_rush_station_coord_progress'

type Point = [number, number]

function loadProgress(): Record<string, Point> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveProgress(p: Record<string, Point>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p))
}

const selectedIcon = L.divIcon({
  className: '',
  html: '<div style="width:16px;height:16px;border-radius:50%;background:#3B82F6;border:3px solid #111827;box-shadow:0 0 0 2px white;"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

export default function StationCoordEditor() {
  const [mapData, setMapData] = useState<MapData | null>(null)
  const [progress, setProgress] = useState<Record<string, Point>>(() => loadProgress())
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.getMap().then(setMapData).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    saveProgress(progress)
  }, [progress])

  const stationByName = useMemo(() => {
    const m = new Map<string, Station>()
    mapData?.stations.forEach((s) => m.set(s.name_zh, s))
    return m
  }, [mapData])

  const selectedStation = selectedName ? stationByName.get(selectedName) || null : null
  const selectedPos: Point | null = selectedStation
    ? progress[selectedStation.name_zh] || [selectedStation.lat, selectedStation.lng]
    : null
  const selectedEdited = !!(selectedStation && progress[selectedStation.name_zh])

  function moveSelected(pt: Point) {
    if (!selectedStation) return
    setProgress((prev) => ({ ...prev, [selectedStation.name_zh]: pt }))
  }

  function revertSelected() {
    if (!selectedStation) return
    setProgress((prev) => {
      const next = { ...prev }
      delete next[selectedStation.name_zh]
      return next
    })
  }

  function clearAll() {
    if (!window.confirm('確定要清除所有已記錄的座標修改嗎？此動作無法復原。')) return
    setProgress({})
    setSelectedName(null)
  }

  const editedNames = Object.keys(progress)

  const codeOutput = useMemo(() => {
    if (editedNames.length === 0) return ''
    return editedNames
      .map((name) => {
        const [lat, lng] = progress[name]
        return `    "${name}": (${lat.toFixed(6)}, ${lng.toFixed(6)}),`
      })
      .join('\n')
  }, [editedNames, progress])

  const filteredStations = useMemo(() => {
    if (!mapData) return []
    const q = filter.trim()
    const list = q ? mapData.stations.filter((s) => s.name_zh.includes(q)) : mapData.stations
    return list.slice(0, 30)
  }, [mapData, filter])

  if (error) return <p className="text-rose-400 text-sm">{error}</p>
  if (!mapData) return <p className="text-white/50 text-sm">載入中…</p>

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="搜尋車站名稱…"
          className="bg-white/10 rounded-lg px-3 py-2 text-sm"
        />
        {editedNames.length > 0 && <span className="text-xs text-white/50">已修改 {editedNames.length} 個車站，尚未輸出</span>}
      </div>

      <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
        {filteredStations.map((s) => {
          const edited = !!progress[s.name_zh]
          const active = selectedName === s.name_zh
          return (
            <button
              key={s.id}
              onClick={() => setSelectedName(s.name_zh)}
              className={`text-xs rounded-lg px-2.5 py-1.5 ${active ? 'bg-blue-600' : edited ? 'bg-emerald-700/60' : 'bg-white/10'}`}
            >
              {s.name_zh}
            </button>
          )
        })}
      </div>

      {selectedStation && selectedPos && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm font-bold">
              編輯中：{selectedStation.name_zh}（拖曳藍色圖釘，或點擊地圖上正確位置）
            </p>
            <button onClick={revertSelected} disabled={!selectedEdited} className="text-xs bg-rose-700/60 disabled:opacity-30 rounded-lg px-3 py-1.5">
              還原原始座標
            </button>
          </div>

          <div className="h-[60vh] rounded-xl overflow-hidden">
            <StationMap
              mapData={mapData}
              station={selectedStation}
              position={selectedPos}
              original={[selectedStation.lat, selectedStation.lng]}
              onMove={moveSelected}
            />
          </div>

          <p className="text-xs text-white/60">
            目前座標：{selectedPos[0].toFixed(6)}, {selectedPos[1].toFixed(6)}
            {selectedEdited && (
              <>
                {' '}
                （原始：{selectedStation.lat.toFixed(6)}, {selectedStation.lng.toFixed(6)}）
              </>
            )}
          </p>
        </div>
      )}

      {editedNames.length > 0 && (
        <div className="bg-white/5 rounded-xl p-3 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <p className="font-bold text-sm">輸出程式碼（貼到 seed_stations.py 的 _COORD_OVERRIDES 中）</p>
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
            rows={Math.min(20, editedNames.length + 1)}
            className="w-full bg-black/40 text-emerald-300 font-mono text-xs rounded-lg p-3"
            onFocus={(e) => e.target.select()}
          />
        </div>
      )}
    </div>
  )
}

function StationMap({
  mapData,
  station,
  position,
  original,
  onMove,
}: {
  mapData: MapData
  station: Station
  position: Point
  original: Point
  onMove: (pt: Point) => void
}) {
  const edited = position[0] !== original[0] || position[1] !== original[1]
  return (
    <MapContainer center={original} zoom={16} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitToStation station={station} />
      <ClickCapture onClick={onMove} />

      {mapData.lines.map((line) => {
        const path = mapData.line_paths[String(line.id)] || []
        if (path.length < 2) return null
        return <Polyline key={line.id} positions={path} pathOptions={{ color: line.color_hex, weight: 3, opacity: 0.4 }} />
      })}

      {mapData.stations
        .filter((s) => s.id !== station.id)
        .map((s) => (
          <CircleMarker key={s.id} center={[s.lat, s.lng]} radius={4} pathOptions={{ color: '#374151', weight: 1, fillColor: '#9CA3AF', fillOpacity: 0.8 }}>
            <Tooltip direction="top" offset={[0, -4]}>
              {s.name_zh}
            </Tooltip>
          </CircleMarker>
        ))}

      {edited && (
        <>
          <CircleMarker center={original} radius={7} pathOptions={{ color: '#6B7280', weight: 2, dashArray: '3 3', fillColor: '#6B7280', fillOpacity: 0.3 }}>
            <Tooltip direction="top">原始位置</Tooltip>
          </CircleMarker>
          <Polyline positions={[original, position]} pathOptions={{ color: '#3B82F6', weight: 2, dashArray: '4 4' }} />
        </>
      )}

      <Marker
        position={position}
        icon={selectedIcon}
        draggable
        eventHandlers={{
          dragend: (e) => {
            const marker = e.target as L.Marker
            const pos = marker.getLatLng()
            onMove([pos.lat, pos.lng])
          },
        }}
      >
        <Tooltip permanent direction="top">
          {station.name_zh}
        </Tooltip>
      </Marker>
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

function FitToStation({ station }: { station: Station }) {
  const map = useMap()
  const lastId = useRef<number | null>(null)
  useEffect(() => {
    if (lastId.current === station.id) return
    lastId.current = station.id
    map.setView([station.lat, station.lng], 16)
  }, [station, map])
  return null
}
