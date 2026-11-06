import { apiRequest } from './client'

/** Money and quantities arrive as decimal strings; they are displayed, never recalculated. */
export type OrderStatus = 'PENDING' | 'CREDIT_HOLD' | 'ON_HOLD' | 'CLARIFICATION_REQUIRED' | 'APPROVED' | 'REJECTED'
export type OrderSource = 'MANUAL' | 'AI' | 'SALESMAN'

export interface CartItemInput {
  product_id: string
  quantity: number
  unit: string
}

export interface SchemeInfo {
  scheme_type: string
  description: string
  min_quantity: string
  free_quantity: string
  discount_percentage: string
}

export interface Totals {
  subtotal: string
  discount_total: string
  taxable_amount: string
  gst_amount: string
  grand_total: string
}

export interface QuoteLine {
  product_id: string
  sku: string
  name: string
  pack_size: string
  order_unit: string
  quantity: string
  free_quantity: string
  price_basis: 'PIECE' | 'CASE'
  unit_price: string
  tax_inclusive: boolean
  gst_rate: string
  discount_percentage: string
  discount_amount: string
  taxable_amount: string
  gst_amount: string
  line_total: string
  scheme: SchemeInfo | null
  available_stock: string
  stock_ok: boolean
}

export interface Quote {
  lines: QuoteLine[]
  totals: Totals
  can_order: boolean // all lines in stock
  available_credit: string
  within_credit: boolean // retailers cannot place the order when false
  ordering_restricted_reason?: string | null // the Admin paused ordering for this shop
}

export interface Correction {
  old_product_id: string | null
  new_product_id: string
  old_quantity: string
  new_quantity: string
  reason: string | null
  created_at: string
}

export interface OrderItem {
  id: string
  product_id: string
  product_name: string
  sku: string
  pack_size: string
  order_unit: string
  paid_quantity: string
  free_quantity: string
  price_basis: 'PIECE' | 'CASE'
  unit_price: string
  tax_inclusive: boolean | null
  discount_percentage: string
  discount_amount: string
  gst_rate: string
  taxable_amount: string
  gst_amount: string
  line_total: string
  scheme: SchemeInfo | null
  corrections: Correction[]
}

export interface Order extends Totals {
  id: string
  order_number: string
  status: OrderStatus
  source: OrderSource
  retailer: { id: string; shop_name: string; city: string; owner_name: string; phone: string; address: string; gstin: string | null }
  remarks: string | null
  hold_reason: string | null
  rejection_reason: string | null
  clarification_message: string | null
  created_at: string
  approved_at: string | null
  approved_by: { id: string; name: string; role: string } | null
  tally_exported_at: string | null
  created_by: { id: string; name: string; role: string }
  created_offline: boolean
  client_created_at: string | null
  client_order_id: string | null
  ai: { extraction_id: string; original_message: string } | null
  items: OrderItem[]
}

export interface OrderSummary {
  id: string
  order_number: string
  status: OrderStatus
  source: OrderSource
  retailer: { id: string; shop_name: string; city: string }
  item_count: number
  grand_total: string
  created_at: string
  created_offline: boolean
  client_order_id: string | null
}

export interface OrderPage {
  items: OrderSummary[]
  page: number
  limit: number
  total: number
}

export const quoteCart = (token: string, items: CartItemInput[], signal?: AbortSignal, retailerId?: string) =>
  apiRequest<Quote>('/orders/quote', { method: 'POST', token, body: { items, retailer_id: retailerId ?? null }, signal })

export const placeOrder = (token: string, items: CartItemInput[], remarks?: string) =>
  apiRequest<Order>('/orders', { method: 'POST', token, body: { items, remarks: remarks || null } })

export const listOrders = (
  token: string,
  params: { status?: OrderStatus[]; source?: OrderSource; search?: string; page?: number; limit?: number; created_by_me?: boolean; retailer_id?: string },
  signal?: AbortSignal,
) => apiRequest<OrderPage>('/orders', { token, params: { ...params, created_by_me: params.created_by_me ? 'true' : undefined }, signal })

export const getOrder = (token: string, id: string, signal?: AbortSignal) =>
  apiRequest<Order>(`/orders/${id}`, { token, signal })

export const correctOrderItem = (
  token: string,
  orderId: string,
  itemId: string,
  body: { new_product_id?: string; new_quantity?: number; unit?: string; reason?: string },
) => apiRequest<Order>(`/orders/${orderId}/items/${itemId}`, { method: 'PATCH', token, body })

export const approveOrder = (token: string, id: string, creditOverrideReason?: string, acknowledgeChanges = false) =>
  apiRequest<Order>(`/orders/${id}/approve`, {
    method: 'POST',
    token,
    body: { credit_override_reason: creditOverrideReason || null, acknowledge_changes: acknowledgeChanges },
  })

export const requestClarification = (token: string, id: string, message: string) =>
  apiRequest<Order>(`/orders/${id}/clarification`, { method: 'POST', token, body: { message } })

export const rejectOrder = (token: string, id: string, reason?: string) =>
  apiRequest<Order>(`/orders/${id}/reject`, { method: 'POST', token, body: { reason: reason ?? null } })

