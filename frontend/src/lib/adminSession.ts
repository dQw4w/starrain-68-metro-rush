import type { LoginResponse } from '../types'

const KEY = 'metro_rush_admin_session'

export function saveAdminSession(session: LoginResponse) {
  localStorage.setItem(KEY, JSON.stringify(session))
}

export function loadAdminSession(): LoginResponse | null {
  const raw = localStorage.getItem(KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function clearAdminSession() {
  localStorage.removeItem(KEY)
}

export function getDeviceId(): string {
  let id = localStorage.getItem('metro_rush_device_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('metro_rush_device_id', id)
  }
  return id
}
