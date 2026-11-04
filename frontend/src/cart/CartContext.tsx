import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

/**
 * The cart holds only what the retailer chose (product + cases). Prices, schemes, GST and
 * totals always come from POST /orders/quote; nothing price-related is stored here.
 * Persisted per user in localStorage so it survives a reload.
 */
export interface CartLine {
  product_id: string
  sku: string
  name: string
  pack_size: string
  order_unit: string
  category: string
  quantity: number
}

/** Set when lines came from an AI draft, so the order is placed as that draft (source AI). */
export interface AiDraftLink {
  extractionId: string
  itemByProduct: Record<string, string> // product_id -> extraction item id
}

interface Cart {
  lines: CartLine[]
  ai: AiDraftLink | null
}

interface CartContextValue extends Cart {
  count: number
  quantityOf: (productId: string) => number
  setQuantity: (line: Omit<CartLine, 'quantity'>, quantity: number) => void
  addLines: (lines: CartLine[], ai?: AiDraftLink) => void
  clear: () => void
}

const EMPTY: Cart = { lines: [], ai: null }
const CartContext = createContext<CartContextValue | null>(null)

function load(key: string): Cart {
  try {
    const cart = JSON.parse(localStorage.getItem(key) ?? 'null') as Cart | null
    if (cart && Array.isArray(cart.lines)) return cart
  } catch {
    // ignore a corrupted value
  }
  return EMPTY
}

export function CartProvider({ userId, children }: { userId: string; children: ReactNode }) {
  const key = `dukaanflow.cart.${userId}`
  const [cart, setCart] = useState<Cart>(() => load(key))

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(cart))
  }, [key, cart])

  const setQuantity = useCallback((line: Omit<CartLine, 'quantity'>, quantity: number) => {
    setCart((c) => {
      const rest = c.lines.filter((l) => l.product_id !== line.product_id)
      const existing = c.lines.findIndex((l) => l.product_id === line.product_id)
      if (quantity <= 0) return { ...c, lines: rest }
      const next = { ...line, quantity }
      const lines = existing === -1 ? [...c.lines, next] : c.lines.map((l, i) => (i === existing ? next : l))
      return { ...c, lines }
    })
  }, [])

  const addLines = useCallback((lines: CartLine[], ai?: AiDraftLink) => {
    setCart((c) => {
      const merged = [...c.lines]
      for (const line of lines) {
        const i = merged.findIndex((l) => l.product_id === line.product_id)
        if (i === -1) merged.push(line)
        else merged[i] = { ...merged[i], quantity: line.quantity }
      }
      return { lines: merged, ai: ai ?? c.ai }
    })
  }, [])

  const clear = useCallback(() => setCart(EMPTY), [])

  const value = useMemo<CartContextValue>(
    () => ({
      ...cart,
      count: cart.lines.length,
      quantityOf: (id) => cart.lines.find((l) => l.product_id === id)?.quantity ?? 0,
      setQuantity,
      addLines,
      clear,
    }),
    [cart, setQuantity, addLines, clear],
  )
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCart(): CartContextValue {
  const context = useContext(CartContext)
  if (!context) throw new Error('useCart must be used inside <CartProvider>')
  return context
}
