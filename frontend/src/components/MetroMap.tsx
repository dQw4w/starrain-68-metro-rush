import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { ChallengeTeaser, DevicePosition, MapData, Station, TeamPublic } from '../types'

interface MetroMapProps {
  mapData: MapData
  teams: TeamPublic[]
  challenges?: ChallengeTeaser[]
  gps?: DevicePosition[]
  onStationClick?: (station: Station) => void
  onChallengeClick?: (challenge: ChallengeTeaser) => void
  meetingStationIds?: number[]
  height?: string
}

const DEFAULT_CENTER: [number, number] = [25.045, 121.53]

export default function MetroMap({
  mapData,
  teams,
  challenges = [],
  gps = [],
  onStationClick,
  onChallengeClick,
  meetingStationIds = [],
  height = '100%',
}: MetroMapProps) {
  const teamById = new Map(teams.map((t) => [t.id, t]))
  const claimByStation = new Map(mapData.claims.map((c) => [c.station_id, c]))

  return (
    <MapContainer center={DEFAULT_CENTER} zoom={13} style={{ height, width: '100%' }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {mapData.lines.map((line) => {
        const path = mapData.line_paths[String(line.id)] || []
        if (path.length < 2) return null
        return <Polyline key={line.id} positions={path} pathOptions={{ color: line.color_hex, weight: 4, opacity: 0.75 }} />
      })}

      {mapData.stations.map((station) => {
        const claim = claimByStation.get(station.id)
        const owner = claim?.owner_team_id ? teamById.get(claim.owner_team_id) : undefined
        const color = owner ? owner.color_hex : '#9CA3AF'
        const isMeeting = meetingStationIds.includes(station.id)
        return (
          <CircleMarker
            key={station.id}
            center={[station.lat, station.lng]}
            radius={isMeeting ? 9 : 6}
            pathOptions={{
              color: isMeeting ? '#111827' : '#374151',
              weight: isMeeting ? 3 : 1.5,
              fillColor: color,
              fillOpacity: 0.9,
            }}
            eventHandlers={onStationClick ? { click: () => onStationClick(station) } : undefined}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <div>
                <div style={{ fontWeight: 700 }}>{station.name_zh}</div>
                {owner && (
                  <div>
                    {owner.name} · {claim?.value} 枚代幣
                  </div>
                )}
              </div>
            </Tooltip>
          </CircleMarker>
        )
      })}

      {challenges.map(
        (ch) =>
          ch.lat != null &&
          ch.lng != null && (
            <CircleMarker
              key={`c-${ch.id}`}
              center={[ch.lat, ch.lng]}
              radius={9}
              pathOptions={{ color: '#5B21B6', weight: 2, fillColor: '#A78BFA', fillOpacity: 0.95 }}
              eventHandlers={onChallengeClick ? { click: () => onChallengeClick(ch) } : undefined}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                {ch.name}
              </Tooltip>
            </CircleMarker>
          )
      )}

      {gps.map((p) => (
        <CircleMarker
          key={p.device_id}
          center={[p.lat, p.lng]}
          radius={5}
          pathOptions={{ color: '#111827', weight: 2, fillColor: '#38BDF8', fillOpacity: 1 }}
        >
          <Tooltip>更新於 {new Date(p.updated_at).toLocaleTimeString('zh-TW')}</Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
