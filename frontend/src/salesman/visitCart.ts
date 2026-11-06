import { useEffect, useState } from 'react'

/** The order being built during a visit: product id -> cases. Kept in localStorage per visit,
 *  so it survives moving between the visit and review screens or closing the app. */
const key = (visitId: string) => `dukaanflow.salesman.cart.${visitId}`

export function useVisitCart(visitId: string | undefined) {
  const [cart, setCart] = useState<Record<string, number>>(() => (visitId ? JSON.parse(localStorage.getItem(key(visitId)) ?? '{}') : {}))
  useEffect(() => {
    if (visitId) localStorage.setItem(key(visitId), JSON.stringify(cart))
  }, [visitId, cart])
  const setQty = (productId: string, n: number) =>
    setCart((c) => {
      const next = { ...c }
      if (n > 0) next[productId] = n
      else delete next[productId]
      return next
    })
  return { cart, setQty }
}

export const clearVisitCart = (visitId: string) => localStorage.removeItem(key(visitId))
