import type { AuthUser, TokenData } from '../api/auth'

/**
 * The backend issues a bearer JWT (30 minutes, no refresh token in V1). It is never logged.
 *
 * - Retailers and office staff: kept in sessionStorage (survives a reload, not closing the
 *   tab) and dropped as soon as it expires.
 * - Salesmen: kept in localStorage with their profile, so the app still opens without
 *   internet in a shop (offline orders are stored on the device). An expired salesman
 *   session is kept for offline use; online, they must log in again before syncing.
 */
const KEY = 'dukaanflow.session'

export interface StoredSession {
  token: string
  expiresAt: number // epoch ms
  user?: AuthUser
}

const storageFor = (user?: AuthUser) => (user?.role === 'SALESMAN' ? localStorage : sessionStorage)

export function saveSession(data: TokenData): StoredSession {
  const session: StoredSession = { token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000, user: data.user }
  clearSession()
  storageFor(data.user).setItem(KEY, JSON.stringify(session))
  return session
}

export const isExpired = (session: StoredSession) => session.expiresAt <= Date.now()

/** A usable session: unexpired, or an expired salesman session (offline use only). */
export function loadSession(): StoredSession | null {
  for (const storage of [sessionStorage, localStorage]) {
    try {
      const session = JSON.parse(storage.getItem(KEY) ?? 'null') as StoredSession | null
      if (!session?.token) continue
      if (!isExpired(session) || session.user?.role === 'SALESMAN') return session
    } catch {
      // corrupted value: ignore
    }
  }
  clearSession()
  return null
}

export function clearSession() {
  sessionStorage.removeItem(KEY)
  localStorage.removeItem(KEY)
}
