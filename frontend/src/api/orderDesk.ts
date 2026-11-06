import { apiDownload, apiRequest } from './client'
import type { Order, OrderSource, OrderStatus } from './orders'

/** Order Desk (ORDER_DESK / ADMIN). Order actions themselves are in api/orders.ts. */
export type DeskView = 'incoming' | 'clarification' | 'confirmed' | 'rejected' | 'all'
export type DeskSort = 'newest' | 'oldest' | 'value_desc' | 'value_asc'

export interface DeskWarning {
  code: string
  severity: 'error' | 'warning'
  message: string
}

export interface Person {
  id: string
  name: string
  phone: string
}

export interface OrderEvent {
  action: 'RECEIVED' | 'CONFIRMED' | 'CREDIT_HOLD' | 'PUT_ON_HOLD' | 'CLARIFICATION_REQUESTED' | 'CORRECTED' | 'REJECTED' | 'EXPORTED'
  actor: { id: string; name: string; role: string } | null
  message: string | null
  details: Record<string, unknown> | null
  created_at: string
}

export interface DeskOrderRow {
  id: string
  order_number: string
  status: OrderStatus
  source: OrderSource
  retailer: { id: string; shop_name: string; owner_name: string; phone: string; city: string }
  salesman: Person | null
  created_by: { id: string; name: string; role: string }
  item_count: number
  grand_total: string
  created_at: string
  approved_at: string | null
  approved_by: { id: string; name: string; role: string } | null
  created_offline: boolean
  tally_exported_at: string | null
  reason: string | null
  warnings: DeskWarning[]
  last_action: OrderEvent | null
}

export interface DeskOrderPage {
  items: DeskOrderRow[]
  page: number
  limit: number
  total: number
}

export interface DeskFilters {
  view: DeskView
  status?: OrderStatus[]
  source?: OrderSource
  search?: string
  salesman_id?: string
  retailer_id?: string
  from_date?: string
  to_date?: string
  exported?: boolean
  sort?: DeskSort
  page?: number
  limit?: number
}

export interface OrderReview {
  order: Order
  salesman: Person | null
  credit: { credit_limit: string; current_outstanding: string; reserved_for_review: string; available_credit: string } | null
  stock: { item_id: string; needed: string; available: string; ok: boolean }[]
  warnings: DeskWarning[]
  ai_input_type: 'TEXT' | 'IMAGE' | 'VOICE' | null
  ai_lines: {
    original_text: string; extracted_name: string; quantity: string | null; unit: string | null
    product: { id: string; sku: string; name: string; pack_size: string } | null
    confidence: string; requires_clarification: boolean; clarification_reason: string | null
    evidence: string[]; alternatives: { sku?: string; name?: string; pack_size?: string }[]
  }[]
  history: OrderEvent[]
}

export interface DeskOverview {
  received_today: number
  pending_review: number
  awaiting_clarification: number
  confirmed_today: number
  confirmed_total: number
  rejected_today: number
  rejected_total: number
  with_stock_or_credit_issues: number
  not_exported: number
}

export interface ProductTotal {
  product_id: string
  sku: string
  name: string
  pack_size: string
  order_unit: string
  paid: string
  free: string
  total: string
  orders: number
}

export interface DispatchStop {
  retailer_id: string
  shop_name: string
  owner_name: string
  phone: string
  address: string
  city: string
  grand_total: string
  orders: { order_id: string; order_number: string; grand_total: string; approved_at: string | null }[]
  products: ProductTotal[]
}

export interface Dispatch {
  order_count: number
  grand_total: string
  products: ProductTotal[]
  beats: { salesman: Person | null; stops: DispatchStop[]; products: ProductTotal[]; orders_count: number; grand_total: string }[]
}

export const fetchOverview = (token: string, signal?: AbortSignal) =>
  apiRequest<DeskOverview>('/order-desk/overview', { token, signal })

export const listDeskOrders = (token: string, f: DeskFilters, signal?: AbortSignal) =>
  apiRequest<DeskOrderPage>('/order-desk/orders', {
    token,
    signal,
    params: { ...f, exported: f.exported === undefined ? undefined : String(f.exported) },
  })

export const fetchOrderReview = (token: string, id: string, signal?: AbortSignal) =>
  apiRequest<OrderReview>(`/order-desk/orders/${id}`, { token, signal })

export const fetchSalesmen = (token: string, signal?: AbortSignal) =>
  apiRequest<Person[]>('/order-desk/salesmen', { token, signal })

export const fetchDispatch = (token: string, p: { from_date?: string; to_date?: string; salesman_id?: string }, signal?: AbortSignal) =>
  apiRequest<Dispatch>('/order-desk/dispatch', { token, signal, params: p })

/** Export confirmed orders to Tally and mark them exported (already exported ones are skipped
 *  unless includeExported). */
export async function exportToTally(
  token: string,
  body: { order_ids?: string[]; from_date?: string; to_date?: string; include_exported?: boolean },
) {
  const result = await apiDownload('/exports/tally', token, {}, body)
  return { ...result, count: Number(result.headers.get('x-exported-count') ?? 0) }
}
