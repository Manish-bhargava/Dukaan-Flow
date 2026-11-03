import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, type AuthUser, type TokenData } from '../api/auth'
import { clearSession, loadSession, saveSession, type StoredSession } from './session'

type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous'; notice?: string }
  | { status: 'authenticated'; user: AuthUser; session: StoredSession }

interface AuthContextValue {
  state: AuthState
  signIn: (data: TokenData) => void
  /** Clear the session; `notice` is shown on the login page (e.g. "session expired"). */
  signOut: (notice?: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export const SESSION_EXPIRED = 'Your session has expired. Please log in again.'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => (loadSession() ? { status: 'loading' } : { status: 'anonymous' }))

  // On page load, confirm a stored token with GET /auth/me (the backend also re-checks the
  // account is active and the role unchanged).
  useEffect(() => {
    const session = loadSession()
    if (!session) return
    const controller = new AbortController()
    fetchMe(session.token, controller.signal)
      .then((res) => setState({ status: 'authenticated', user: res.data, session }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        clearSession()
        setState({ status: 'anonymous', notice: err instanceof Error ? err.message : SESSION_EXPIRED })
      })
    return () => controller.abort()
  }, [])

  const signIn = useCallback((data: TokenData) => {
    setState({ status: 'authenticated', user: data.user, session: saveSession(data) })
  }, [])

  const signOut = useCallback((notice?: string) => {
    clearSession()
    setState({ status: 'anonymous', notice })
  }, [])

  // Log out when the token expires (no refresh tokens in V1).
  const expiresAt = state.status === 'authenticated' ? state.session.expiresAt : null
  useEffect(() => {
    if (expiresAt === null) return
    const timer = window.setTimeout(() => signOut(SESSION_EXPIRED), Math.max(0, expiresAt - Date.now()))
    return () => window.clearTimeout(timer)
  }, [expiresAt, signOut])

  const value = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
