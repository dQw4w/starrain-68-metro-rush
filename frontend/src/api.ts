import type {
  ActionLogEntry,
  ApprovalRequest,
  Challenge,
  ChallengeAttempt,
  ChallengeTeaser,
  DevicePosition,
  GameConfig,
  GamePhase,
  LineStationOrderEntry,
  LoginResponse,
  MapData,
  TeamAdminView,
  TeamPublic,
  TeamState,
} from './types'

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

export const api = {
  // --- Public map ---
  getMap: () => req<MapData>('/map'),
  getActiveChallenges: () => req<ChallengeTeaser[]>('/map/challenges'),

  // --- Auth ---
  login: (pin: string) => req<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ pin }) }),
  loginByLink: (adminToken: string) =>
    req<LoginResponse>(`/auth/login-link/${adminToken}`, { method: 'POST' }),
  logout: (token: string) =>
    req<{ ok: boolean }>('/auth/logout', { method: 'POST', headers: authHeaders(token) }),
  adminWsTicket: (token: string) =>
    req<{ ticket: string }>('/auth/ws-ticket', { method: 'POST', headers: authHeaders(token) }),

  // --- Team (share-token scoped) ---
  teamState: (token: string) => req<TeamState>(`/team/${token}/state`),
  teamLog: (token: string, actionType?: string) =>
    req<ActionLogEntry[]>(`/team/${token}/log${actionType ? `?action_type=${actionType}` : ''}`),
  teamAction: (token: string, station_id: number, kind: 'claim' | 'topup', amount: number) =>
    req<any>(`/team/${token}/action`, { method: 'POST', body: JSON.stringify({ station_id, kind, amount }) }),
  getPublicConfig: () => req<{ starting_chips: number; max_deposit_per_visit: number; fail_bonus_step_pct: number }>('/config/public'),
  challengeStart: (token: string, challengeId: number, body: { called_shot_value?: number; target_team_id?: number }) =>
    req<any>(`/team/${token}/challenge/${challengeId}/start`, { method: 'POST', body: JSON.stringify(body) }),
  challengeSubmitResult: (token: string, challengeId: number, achieved_value?: number) =>
    req<any>(`/team/${token}/challenge/${challengeId}/submit-result`, {
      method: 'POST',
      body: JSON.stringify({ achieved_value }),
    }),
  myAttempts: (token: string) => req<ChallengeAttempt[]>(`/team/${token}/my-attempts`),
  challengeDetail: (token: string, challengeId: number) => req<Challenge>(`/team/${token}/challenge/${challengeId}`),
  gpsPing: (token: string, device_id: string, lat: number, lng: number) =>
    req<any>(`/team/${token}/gps`, { method: 'POST', body: JSON.stringify({ device_id, lat, lng }) }),
  teamGps: (token: string) => req<DevicePosition[]>(`/team/${token}/gps`),
  teamWsTicket: (token: string) => req<{ ticket: string }>(`/team/${token}/ws-ticket`, { method: 'POST' }),

  // --- Team admin ---
  adminTeamInfo: (token: string, teamId: number) =>
    req<TeamPublic>(`/admin/team/${teamId}/info`, { headers: authHeaders(token) }),
  adminPending: (token: string, teamId: number) =>
    req<ApprovalRequest[]>(`/admin/team/${teamId}/pending`, { headers: authHeaders(token) }),
  adminApprove: (token: string, teamId: number, requestId: number, body?: { success: boolean; achieved_value?: number }) =>
    req<any>(`/admin/team/${teamId}/approve/${requestId}`, {
      method: 'POST',
      headers: authHeaders(token),
      body: body ? JSON.stringify(body) : undefined,
    }),
  adminDeny: (token: string, teamId: number, requestId: number) =>
    req<any>(`/admin/team/${teamId}/deny/${requestId}`, { method: 'POST', headers: authHeaders(token) }),
  adminGps: (token: string, teamId: number) =>
    req<DevicePosition[]>(`/admin/team/${teamId}/gps`, { headers: authHeaders(token) }),
  adminLog: (token: string, teamId: number) =>
    req<ActionLogEntry[]>(`/admin/team/${teamId}/log`, { headers: authHeaders(token) }),
  adminAdjustChips: (token: string, teamId: number, delta: number, reason: string) =>
    req<any>(`/admin/team/${teamId}/adjust-chips`, {
      method: 'POST',
      headers: authHeaders(token),
      body: JSON.stringify({ delta, reason }),
    }),

  // --- Super admin ---
  getConfig: (token: string) => req<GameConfig>('/superadmin/config', { headers: authHeaders(token) }),
  updateConfig: (token: string, body: Partial<GameConfig>) =>
    req<GameConfig>('/superadmin/config', { method: 'PUT', headers: authHeaders(token), body: JSON.stringify(body) }),
  getPhase: () => req<GamePhase>('/superadmin/phase'),
  listTeams: (token: string) => req<TeamAdminView[]>('/superadmin/teams', { headers: authHeaders(token) }),
  createTeam: (
    token: string,
    body: { name: string; color_hex: string; meeting_station_id?: number }
  ) => req<TeamAdminView>('/superadmin/teams', { method: 'POST', headers: authHeaders(token), body: JSON.stringify(body) }),
  updateTeam: (token: string, teamId: number, body: Record<string, any>) =>
    req<TeamAdminView>(`/superadmin/teams/${teamId}`, {
      method: 'PUT',
      headers: authHeaders(token),
      body: JSON.stringify(body),
    }),
  regenerateAdminLink: (token: string, teamId: number) =>
    req<TeamAdminView>(`/superadmin/teams/${teamId}/regenerate-admin-link`, {
      method: 'POST',
      headers: authHeaders(token),
    }),
  deleteTeam: (token: string, teamId: number) =>
    req<{ ok: boolean }>(`/superadmin/teams/${teamId}`, { method: 'DELETE', headers: authHeaders(token) }),
  overview: (token: string) => req<{ ranking: (TeamPublicWithPending)[] }>('/superadmin/overview', { headers: authHeaders(token) }),
  globalLog: (token: string) => req<ActionLogEntry[]>('/superadmin/log', { headers: authHeaders(token) }),

  createLine: (token: string, body: { code: string; name_zh: string; name_en: string; color_hex: string; sort_order?: number }) =>
    req<any>('/superadmin/lines', { method: 'POST', headers: authHeaders(token), body: JSON.stringify(body) }),
  listLines: (token: string) => req<any[]>('/superadmin/lines', { headers: authHeaders(token) }),
  createStation: (
    token: string,
    body: { name_zh: string; name_en: string; lat: number; lng: number; lines: { line_id: number; sequence: number }[] }
  ) => req<any>('/superadmin/stations', { method: 'POST', headers: authHeaders(token), body: JSON.stringify(body) }),
  updateStation: (token: string, stationId: number, body: Record<string, any>) =>
    req<any>(`/superadmin/stations/${stationId}`, {
      method: 'PUT',
      headers: authHeaders(token),
      body: JSON.stringify(body),
    }),
  lineStationOrder: (token: string) =>
    req<Record<string, LineStationOrderEntry[]>>('/superadmin/line-station-order', { headers: authHeaders(token) }),

  listAllChallenges: (token: string) => req<Challenge[]>('/superadmin/challenges', { headers: authHeaders(token) }),
  createChallenge: (token: string, body: Partial<Challenge>) =>
    req<Challenge>('/superadmin/challenges', { method: 'POST', headers: authHeaders(token), body: JSON.stringify(body) }),
  updateChallenge: (token: string, id: number, body: Partial<Challenge>) =>
    req<Challenge>(`/superadmin/challenges/${id}`, { method: 'PUT', headers: authHeaders(token), body: JSON.stringify(body) }),
  activatePool: (token: string) =>
    req<any>('/superadmin/challenges/activate-pool', { method: 'POST', headers: authHeaders(token) }),
}

interface TeamPublicWithPending {
  id: number
  name: string
  color_hex: string
  chips_balance: number
  stations_owned: number
  rank: number
  pending_count: number
}
