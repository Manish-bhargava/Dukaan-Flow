import { useState } from 'react'
import { admin } from '../../api/admin'
import { useErrorMessage, useLoad } from '../../auth/useApi'

/** Hooks shared by the admin screens. */

/** Run an action with busy/error state; the error is the backend's message (an expired session signs out, as everywhere else). */
export function useAction() {
  const toMessage = useErrorMessage()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /** Resolves true when `fn` succeeded. */
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true)
    setError('')
    try {
      await fn()
      return true
    } catch (err) {
      setError(toMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, setError, run }
}

export function useSalesmanOptions(withNone = true): [string, string][] {
  const salesmen = useLoad((t, s) => admin.salesmen(t, s), 'admin-salesmen-options')
  const list = salesmen.state.status === 'ready' ? salesmen.state.data.filter((u) => u.is_active) : []
  return [['', 'All salesmen'], ...(withNone ? [['none', 'Not assigned'] as [string, string]] : []), ...list.map((u) => [u.id, u.name] as [string, string])]
}

export function useCatalogueOptions() {
  const categories = useLoad((t, s) => admin.categories(t, s), 'admin-categories')
  const brands = useLoad((t, s) => admin.brands(t, s), 'admin-brands')
  return {
    categories: categories.state.status === 'ready' ? categories.state.data : [],
    brands: brands.state.status === 'ready' ? brands.state.data : [],
  }
}
