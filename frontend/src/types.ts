export type ChallengeType = 'fixed' | 'variable' | 'steal' | 'multiplier'
export type PoolState = 'queued' | 'active' | 'retired'
export type RequestKind = 'claim' | 'topup' | 'challenge_start' | 'challenge_result'
export type RequestStatus = 'pending' | 'approved' | 'denied' | 'stale'
export type AttemptStatus = 'pending_start_approval' | 'in_progress' | 'pending_result' | 'success' | 'failed'
export type GamePhaseName = 'not_started' | 'active' | 'lunch_break' | 'ended' | 'paused'

export interface Line {
  id: number
  code: string
  name_zh: string
  name_en: string
  color_hex: string
  sort_order: number
}

export interface Station {
  id: number
  name_zh: string
  name_en: string
  lat: number
  lng: number
  line_ids: number[]
}

export interface StationClaim {
  station_id: number
  owner_team_id: number | null
  value: number
  updated_at: string
}

export interface MapData {
  lines: Line[]
  stations: Station[]
  claims: StationClaim[]
  /** Ordered [lat, lng] points per line_id (stations + invisible waypoints interleaved), ready to draw. */
  line_paths: Record<string, [number, number][]>
}

export interface LineStationOrderEntry {
  station_id: number
  name_zh: string
  lat: number
  lng: number
  sequence: number
}

export interface TeamPublic {
  id: number
  name: string
  color_hex: string
  meeting_station_id: number | null
  chips_balance: number
  active: boolean
  stations_owned: number
  rank: number
}

export interface TeamAdminView extends TeamPublic {
  share_token: string
}

export interface TeamSelf {
  id: number
  name: string
  color_hex: string
  meeting_station_id: number | null
  chips_balance: number
  share_token: string
}

export interface GamePhase {
  phase: GamePhaseName
  server_time: string
  game_date: string
  start_at: string
  end_at: string
  lunch_start_at: string
  lunch_end_at: string
}

export interface GameConfig {
  team_count: number
  game_date: string
  start_time: string
  end_time: string
  lunch_start: string
  lunch_end: string
  starting_chips: number
  max_deposit_per_visit: number
  fail_bonus_step_pct: number
  challenge_pool_initial: number
  challenge_pool_refill: number
  challenge_pool_max: number
  override_status: 'auto' | 'paused' | 'force_ended'
  locked: boolean
}

export interface ApprovalRequest {
  id: number
  kind: RequestKind
  team_id: number
  station_id: number | null
  challenge_id: number | null
  challenge_attempt_id: number | null
  requested_by: string | null
  requested_value: Record<string, any>
  status: RequestStatus
  resolved_by: number | null
  resolved_at: string | null
  created_at: string
}

export interface Challenge {
  id: number
  name: string
  description: string
  type: ChallengeType
  reward_config: Record<string, any>
  location_name: string | null
  lat: number | null
  lng: number | null
  image_url: string | null
  pool_state: PoolState
}

/** Public listing shape: no `description` — hidden until a team's admin approves the start. */
export type ChallengeTeaser = Omit<Challenge, 'description'>

export interface ChallengeAttempt {
  id: number
  challenge_id: number
  team_id: number
  status: AttemptStatus
  called_shot_value: number | null
  achieved_value: number | null
  target_team_id: number | null
  fail_bonus_pct_locked: number
  reward_amount: number | null
  started_at: string | null
  resolved_at: string | null
}

export interface ActionLogEntry {
  id: number
  team_id: number
  actor: string
  action_type: string
  station_id: number | null
  challenge_id: number | null
  chip_delta: number | null
  resulting_balance: number | null
  message: string
  created_at: string
}

export interface DevicePosition {
  team_id: number
  device_id: string
  lat: number
  lng: number
  updated_at: string
}

export interface TeamState {
  team: TeamSelf
  phase: GamePhase
  ranking: TeamPublic[]
  pending_requests: ApprovalRequest[]
}

export interface LoginResponse {
  token: string
  admin_id: number
  team_id: number | null
  display_name: string
  is_super: boolean
}
