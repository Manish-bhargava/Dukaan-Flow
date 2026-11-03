import type { TokenData } from '../api/auth'

/**
 * The backend issues a bearer JWT (30 minutes, no refresh token in V1). It is kept in
 * sessionStorage so it survives a reload but not closing the tab, and is dropped as soon
 * as it expires. It is never logged.
 */
const KEY = 'dukaanflow.session'

export interface StoredSession {
  token: string
  expiresAt: number // epoch ms
}

export function saveSession(data: TokenData): StoredSession {
  const session = { token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 }
  sessionStorage.setItem(KEY, JSON.stringify(session))
  return session
}

export function loadSession(): StoredSession | null {
  try {
    const session = JSON.parse(sessionStorage.getItem(KEY) ?? 'null') as StoredSession | null
    if (session?.token && session.expiresAt > Date.now()) return session
  } catch {
    // corrupted value: fall through and clear it
  }
  clearSession()
  return null
}

export function clearSession() {
  sessionStorage.removeItem(KEY)
}
