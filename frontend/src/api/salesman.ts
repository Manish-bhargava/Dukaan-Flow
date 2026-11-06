import { apiRequest } from './client'
import type { Order } from './orders'
import type { Category, Scheme } from './products'

export interface BundleRetailer {
  id: string
  shop_name: string
  owner_name: string
  phone: string
  address: string
  city: string
  gstin: string | null
  registered_mobiles: string[] // login mobile(s) of the retailer's account
  ordering_restricted_reason?: string | null // the Admin paused ordering for this shop
  last_order_at: string | null
  credit: { credit_limit: string; current_outstanding: string; reserved_for_review: string; available_credit: string } | null
  recent_orders: { id: string; order_number: string; created_at: string; grand_total: string; status: Order['status']; item_count: number }[]
}

export interface BundleProduct {
  id: string
  sku: string
  name: string
  brand: string
  category: Category
  pack_size: string
  units_per_case: string
  base_unit: string
  order_unit: string
  gst_rate: string
  image_url: string | null
  thumbnail_url: string | null
  stock_cases: string
  in_stock: boolean
  schemes: Scheme[]
}

export interface BundlePrice {
  dealer_price: string
  price_basis: 'PIECE' | 'CASE'
  tax_inclusive: boolean
  case_price: string
}

/** Everything the salesman app keeps on the phone for offline use. */
export interface SyncBundle {
  synced_at: string
  retailers: BundleRetailer[]
  categories: Category[]
  products: BundleProduct[]
  prices: Record<string, Record<string, BundlePrice>> // retailer_id -> product_id -> price
}

export const fetchSyncBundle = (token: string, signal?: AbortSignal) =>
  apiRequest<SyncBundle>('/salesman/sync-bundle', { token, signal })

/** Today's work as recorded on the server. */
export interface SalesmanHome {
  date: string
  assigned_retailers: number
  visits_today: number
  orders_today: number
  todays_visits: { id: string; retailer_id: string; shop_name: string; started_at: string; ended_at: string | null; outcome: 'ORDER_PLACED' | 'NO_ORDER' | null }[]
}

/** After each sync run: what is still in the phone's outbox (shown to the Admin). */
export const reportSyncStatus = (token: string, body: { pending_orders: number; failed_orders: number; pending_visits: number; last_error: string | null }) =>
  apiRequest<object>('/salesman/sync-status', { method: 'POST', token, body })

export const fetchSalesmanHome = (token: string, signal?: AbortSignal) =>
  apiRequest<SalesmanHome>('/salesman/home', { token, signal })

export interface VisitBody {
  id: string
  retailer_id: string
  started_at: string
  ended_at: string | null
  outcome: 'ORDER_PLACED' | 'NO_ORDER' | null
  client_order_id: string | null
}

export const sendVisit = (token: string, visit: VisitBody) =>
  apiRequest<{ id: string; order_id: string | null }>('/salesman/visits', { method: 'POST', token, body: visit })

export interface SalesmanOrderBody {
  retailer_id: string
  items: { product_id: string; quantity: number; unit: string; expected_unit_price: string; expected_scheme_ids?: string[] }[]
  remarks: string | null
  client_order_id: string
  created_offline: boolean
  client_created_at: string
}

/** The normal order API; the client id makes retries safe (same order, never a duplicate). */
export const sendSalesmanOrder = (token: string, body: SalesmanOrderBody) =>
  apiRequest<Order>('/orders', { method: 'POST', token, body })
