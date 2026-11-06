import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, type AuthUser, type TokenData } from '../api/auth'
import { ApiError } from '../api/client'
import { clearSession, isExpired, loadSession, saveSession, type StoredSession } from './session'

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
const SALESMAN_EXPIRED = 'Your session has expired. Log in again to sync your saved orders (they are kept on this phone).'

/** Without internet a salesman keeps working with the saved session (offline mode). */
const offlineSalesman = (session: StoredSession) => session.user?.role === 'SALESMAN' && !navigator.onLine

function initialState(): AuthState {
  const session = loadSession()
  if (!session) return { status: 'anonymous' }
  if (session.user && offlineSalesman(session)) return { status: 'authenticated', user: session.user, session }
  if (isExpired(session)) {
    // Only expired salesman sessions are kept, for offline use; online they log in again.
    clearSession()
    return { status: 'anonymous', notice: SALESMAN_EXPIRED }
  }
  // Open at once with the stored user (one fewer round trip on slow 3G); GET /auth/me below
  // still confirms it, and every API call is checked by the server anyway.
  if (session.user) return { status: 'authenticated', user: session.user, session }
  return { status: 'loading' }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(initialState)

  // On page load, confirm a stored token with GET /auth/me in the background (the backend also
  // re-checks the account is active and the role unchanged); a refusal signs out. Offline
  // salesmen skip this.
  useEffect(() => {
    const session = loadSession()
    if (!session || offlineSalesman(session) || isExpired(session)) return
    const controller = new AbortController()
    fetchMe(session.token, controller.signal)
      .then((res) => setState({ status: 'authenticated', user: res.data, session }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof ApiError && err.status === 0 && session.user?.role === 'SALESMAN') {
          setState({ status: 'authenticated', user: session.user, session }) // server unreachable: offline mode
          return
        }
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

  // Log out when the token expires (no refresh tokens in V1). A salesman without internet
  // keeps working offline and is asked to log in again once back online.
  const session = state.status === 'authenticated' ? state.session : null
  const role = state.status === 'authenticated' ? state.user.role : null
  useEffect(() => {
    if (!session) return
    const expire = () => {
      if (role === 'SALESMAN' && !navigator.onLine) return
      signOut(role === 'SALESMAN' ? SALESMAN_EXPIRED : SESSION_EXPIRED)
    }
    const timer = window.setTimeout(expire, Math.max(0, session.expiresAt - Date.now()))
    const onOnline = () => isExpired(session) && expire()
    window.addEventListener('online', onOnline)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('online', onOnline)
    }
  }, [session, role, signOut])

  const value = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
