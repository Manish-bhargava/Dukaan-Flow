import { useCallback, useEffect, useState } from 'react'
import { ApiError, type ApiResponse } from '../api/client'
import { SESSION_EXPIRED, useAuth } from './AuthContext'

/** The signed-in user's token (screens using it are only rendered when signed in). */
export function useToken(): string {
  const { state } = useAuth()
  return state.status === 'authenticated' ? state.session.token : ''
}

/** Returns a handler that turns an API error into a message, ending the session on 401/disabled. */
export function useErrorMessage() {
  const { signOut } = useAuth()
  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError && (err.status === 401 || err.code === 'ACCOUNT_DISABLED')) {
        signOut(err.status === 401 ? SESSION_EXPIRED : err.message)
      }
      return err instanceof Error ? err.message : 'Something went wrong. Please try again.'
    },
    [signOut],
  )
}

type State<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T }

/** Load data for a screen; re-runs when `key` changes. */
export function useLoad<T>(load: (token: string, signal: AbortSignal) => Promise<ApiResponse<T>>, key: string) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [state, setState] = useState<State<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    // Keep showing previous data while reloading (no flicker); `loading` tells the screen.
    setState((s) => (s.status === 'ready' ? s : { status: 'loading' }))
    setLoading(true)
    load(token, controller.signal)
      .then((res) => {
        setState({ status: 'ready', data: res.data })
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setState({ status: 'error', message: toMessage(err) })
        setLoading(false)
      })
    return () => controller.abort()
    // `load` is recreated each render; `key` captures its inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, key, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const setData = useCallback((data: T) => setState({ status: 'ready', data }), [])
  return { state, loading, reload, setData }
}
