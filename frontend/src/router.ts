import { useEffect, useState } from 'react'

/** Minimal client-side routing on the History API (three routes do not need a library). */
const listeners = new Set<() => void>()

export function navigate(to: string, { replace = false } = {}) {
  if (to === window.location.pathname + window.location.hash) return
  window.history[replace ? 'replaceState' : 'pushState'](null, '', to)
  listeners.forEach((notify) => notify())
  if (!to.includes('#')) window.scrollTo(0, 0)
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(window.location.pathname)
  useEffect(() => {
    const update = () => setPathname(window.location.pathname)
    listeners.add(update)
    window.addEventListener('popstate', update)
    return () => {
      listeners.delete(update)
      window.removeEventListener('popstate', update)
    }
  }, [])
  return pathname
}
