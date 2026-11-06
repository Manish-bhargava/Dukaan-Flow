import { useState } from 'react'
import { getOrder } from '../api/orders'
import { useErrorMessage, useToken } from '../auth/useApi'
import { navigate } from '../router'
import { useCart } from './CartContext'
import { orderCartLines } from './lines'

/** Repeat any earlier order: load its items, add them to the cart and open the cart. */
export function useRepeatOrder() {
  const token = useToken()
  const toMessage = useErrorMessage()
  const { addLines } = useCart()
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<{ orderId: string; message: string } | null>(null)

  async function repeat(orderId: string) {
    setBusyId(orderId)
    setError(null)
    try {
      addLines(orderCartLines((await getOrder(token, orderId)).data))
      navigate('/cart')
    } catch (err) {
      setError({ orderId, message: toMessage(err) })
      setBusyId(null)
    }
  }

  return { repeat, busyId, error }
}
