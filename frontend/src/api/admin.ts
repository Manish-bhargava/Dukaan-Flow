import { API_BASE_URL, ApiError, apiDownload, apiRequest } from './client'
import type { OrderSource, OrderStatus } from './orders'

/** Admin API (ADMIN only; enforced by the backend). Money and quantities are decimal strings. */

export type Role = 'RETAILER' | 'SALESMAN' | 'ORDER_DESK' | 'ADMIN'
export type PriceBasis = 'PIECE' | 'CASE'

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  limit: number
}

export interface PersonRef {
  id: string
  name: string
  phone: string
  role: Role
  is_active: boolean
}

export interface AdminUser {
  id: string
  name: string
  phone: string
  email: string | null
  role: Role
  is_active: boolean
  last_login_at: string | null
  created_at: string
  has_password: boolean
  retailer: { id: string; shop_name: string } | null
}

export interface RetailerRow {
  id: string
  shop_name: string
  owner_name: string
  phone: string
  address: string
  city: string
  gstin: string | null
  is_active: boolean
  created_at: string
  ordering_restricted_reason: string | null
  salesman: PersonRef | null
  credit_limit?: string | null
  outstanding?: string | null
  last_order_at?: string | null
  total_purchased?: string
}

export interface OrderBrief {
  id: string
  order_number: string
  status: OrderStatus
  source: OrderSource
  grand_total: string
  created_at: string
  item_count: number
  retailer: { id: string; shop_name: string }
  salesman: string | null
  created_offline: boolean
}

export interface CreditInfo {
  credit_limit: string
  current_outstanding: string
  reserved_for_review: string
  available_credit: string
}

export interface RetailerDetail extends RetailerRow {
  credit: CreditInfo | null
  purchases: { total_orders: number; confirmed_orders: number; total_purchased: string; open_orders: number; rejected_orders: number }
  logins: { id: string; phone: string; email: string | null; is_active: boolean; last_login_at: string | null }[]
  recent_orders: OrderBrief[]
}

export interface Price {
  dealer_price: string
  price_basis: PriceBasis
  tax_inclusive: boolean
  effective_from: string
  effective_to: string | null
}

export interface RetailerPriceRow {
  product: { id: string; sku: string; name: string; brand: string; order_unit: string }
  default: Price | null
  own: Price | null
  effective: Price | null
  schemes: string[]
}

export interface AuditEntry {
  id: string
  at: string
  action: string
  entity_type: string
  entity_id: string | null
  label: string | null
  details: Record<string, unknown> | null
  message: string | null
  actor: { id: string; name: string; role: Role } | null
}

export interface SyncInfo {
  last_sync_at: string | null
  reported_at: string | null
  pending_orders: number
  failed_orders: number
  pending_visits: number
  last_error: string | null
}

export interface SalesmanRow extends AdminUser {
  assigned_retailers: number
  orders_30d: number
  confirmed_value_30d: string
  offline_orders_30d: number
  visits_30d: number
  visits_with_order_30d: number
  last_visit_at: string | null
  sync: SyncInfo | null
}

export interface SyncFailure {
  id: string
  at: string
  client_order_id: string
  salesman: string | null
  error_code: string
  message: string
  retailer_id: string | null
  created_offline: boolean
  items: { product_id: string; quantity: string }[] | null
}

export interface SalesmanDetail extends AdminUser {
  stats_30d: { orders: number; confirmed_value: string; offline_orders: number; visits: number; visits_with_order: number }
  activity: Record<string, number>
  sync: SyncInfo | null
  retailers: (RetailerRow & { outstanding: string | null; credit_limit: string | null })[]
  visits: { id: string; shop_name: string; started_at: string; ended_at: string | null; outcome: string | null; order_id: string | null; order_number: string | null; order_status: OrderStatus | null }[]
  sync_failures: SyncFailure[]
}

export interface ProductRow {
  id: string
  sku: string
  name: string
  brand: string
  category: { id: string; name: string; is_active: boolean }
  pack_size: string
  units_per_case: string
  base_unit: string
  order_unit: string
  gst_rate: string
  is_active: boolean
  thumbnail_url: string | null
  image_url: string | null
  created_at: string
  updated_at: string
  stock: string | null
  default_price?: Price | null
  retailer_prices?: number
  stock_updated_at?: string | null
  last_movement_at?: string | null
}

export interface Movement {
  id: string
  type: 'ORDER_DEDUCTION' | 'RESTOCK' | 'ADJUSTMENT'
  change: string
  stock_after: string | null
  stock_before: string | null
  reason: string | null
  order_id: string | null
  order_number: string | null
  by: string | null
  at: string
}

export interface SchemeRow {
  id: string
  product: { id: string; sku: string; name: string }
  scheme_type: 'FREE_GOODS' | 'SLAB_DISCOUNT'
  description: string
  min_quantity: string
  free_quantity: string
  discount_percentage: string
  starts_at: string
  ends_at: string | null
  is_active: boolean
  state: 'active' | 'upcoming' | 'expired' | 'inactive'
}

export interface ProductDetail extends ProductRow {
  low_stock: number
  default_price: Price | null
  price_history: (Price & { id: string; retailer: { id: string; shop_name: string } | null; by: string | null; created_at: string })[]
  schemes: SchemeRow[]
  movements: Movement[]
}

export interface Named {
  id: string
  name: string
  is_active: boolean
  products: number
}

export interface Dashboard {
  business_name: string
  retailers_total: number
  retailers_active: number
  salesmen_total: number
  salesmen_active: number
  products_total: number
  products_active: number
  orders_today: number
  pending: number
  clarification: number
  confirmed: number
  rejected: number
  confirmed_value_total: string
  confirmed_value_today: string
  confirmed_value_30d: string
  outstanding_total: string
  credit_limit_total: string
  low_stock_threshold: number
  low_stock_count: number
  low_stock: { product: ProductRow; stock: string }[]
  inactive_days: number
  inactive_count: number
  inactive: { retailer: RetailerRow; last_order_at: string | null }[]
  recent_orders: OrderBrief[]
  recent_retailers: RetailerRow[]
  recent_products: ProductRow[]
  recent_visits: { salesman: string; shop_name: string; started_at: string; ended_at: string | null; outcome: string | null; order_number: string | null; order_total: string | null; order_id: string | null }[]
}

export interface Settings {
  business_name: string
  business_address: string
  business_phone: string
  business_gstin: string
  low_stock_cases: number
  inactive_retailer_days: number
  duplicate_window_hours: number
  ai_low_confidence_percent: number
}

export interface Report {
  name: string
  title: string
  uses_dates: boolean
  from_date: string | null
  to_date: string | null
  columns: string[]
  rows: (string | number)[][]
}

type Params = Record<string, string | number | undefined>
const get = <T,>(token: string, path: string, params?: Params, signal?: AbortSignal) =>
  apiRequest<T>(`/admin${path}`, { token, params, signal })
const send = <T,>(token: string, method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', path: string, body?: unknown, params?: Params) =>
  apiRequest<T>(`/admin${path}`, { token, method, body, params })

export const admin = {
  dashboard: (t: string, s?: AbortSignal) => get<Dashboard>(t, '/dashboard', undefined, s),
  orderDesk: (t: string, s?: AbortSignal) => get<{
    overview: Record<string, number>; corrected_orders_30d: number; corrected_orders_total: number; tally_exported: number;
    tally_not_exported: number; people: { id: string; name: string; role: Role; actions: Record<string, number> }[]; recent: AuditEntry[]
  }>(t, '/order-desk', undefined, s),
  audit: (t: string, p: Params, s?: AbortSignal) => get<Paged<AuditEntry>>(t, '/audit', p, s),
  aiOrders: (t: string, p: Params, s?: AbortSignal) => get<Paged<{
    id: string; created_at: string; original_message: string; status: string; model_name: string | null; shop_name: string | null
    input_type: 'TEXT' | 'IMAGE' | 'VOICE'
    lines: { original_text: string; extracted_name: string; quantity: string | null; unit: string | null; confidence: string; alternatives: { sku?: string; name?: string; score?: number }[]; requires_clarification: boolean
      evidence: string[]; clarification_reason: string | null }[]
    order: { id: string; order_number: string; status: OrderStatus; grand_total: string } | null
  }> & { stats: Record<string, number | string | null>; low_confidence_percent: number }>(t, '/ai-orders', p, s),
  sync: (t: string, s?: AbortSignal) => get<{
    salesmen: { salesman: PersonRef; sync: SyncInfo | null }[]; offline_counts: Record<string, number>
    offline_orders: { id: string; order_number: string; status: OrderStatus; grand_total: string; created_at: string; retailer: { id: string; shop_name: string }; hold_reason: string | null; rejection_reason: string | null; client_created_at: string | null; client_order_id: string | null; salesman: string }[]
    failures: SyncFailure[]; failures_7d: number
  }>(t, '/sync', undefined, s),
  settings: (t: string, s?: AbortSignal) => get<Settings>(t, '/settings', undefined, s),
  saveSettings: (t: string, body: Settings) => send<Settings>(t, 'PUT', '/settings', body),

  retailers: (t: string, p: Params, s?: AbortSignal) => get<Paged<RetailerRow>>(t, '/retailers', p, s),
  retailer: (t: string, id: string, s?: AbortSignal) => get<RetailerDetail>(t, `/retailers/${id}`, undefined, s),
  createRetailer: (t: string, body: unknown) => send<{ id: string }>(t, 'POST', '/retailers', body),
  updateRetailer: (t: string, id: string, body: unknown) => send<RetailerDetail>(t, 'PATCH', `/retailers/${id}`, body),
  updateCredit: (t: string, id: string, body: unknown) => send<RetailerDetail>(t, 'PATCH', `/retailers/${id}/credit`, body),
  creditHistory: (t: string, id: string, s?: AbortSignal) => get<{
    ledger: { id: string; type: string; amount: string; description: string | null; order_number: string | null; by: string | null; at: string }[]
    changes: AuditEntry[]
  }>(t, `/retailers/${id}/credit-history`, undefined, s),
  retailerPrices: (t: string, id: string, s?: AbortSignal) => get<RetailerPriceRow[]>(t, `/retailers/${id}/prices`, undefined, s),

  salesmen: (t: string, s?: AbortSignal) => get<SalesmanRow[]>(t, '/salesmen', undefined, s),
  salesman: (t: string, id: string, s?: AbortSignal) => get<SalesmanDetail>(t, `/salesmen/${id}`, undefined, s),
  assign: (t: string, body: { salesman_id: string | null; retailer_ids: string[] }) => send<{ changed: string[] }>(t, 'POST', '/assignments', body),

  users: (t: string, p: Params, s?: AbortSignal) => get<Paged<AdminUser>>(t, '/users', p, s),
  user: (t: string, id: string, s?: AbortSignal) => get<AdminUser & { activity: Record<string, number>; recent: AuditEntry[] }>(t, `/users/${id}`, undefined, s),
  createUser: (t: string, body: unknown) => send<AdminUser>(t, 'POST', '/users', body),
  updateUser: (t: string, id: string, body: unknown) => send<AdminUser>(t, 'PATCH', `/users/${id}`, body),
  resetPassword: (t: string, id: string, newPassword: string) => send<object>(t, 'POST', `/users/${id}/reset-password`, { new_password: newPassword }),

  categories: (t: string, s?: AbortSignal) => get<Named[]>(t, '/categories', undefined, s),
  createCategory: (t: string, name: string) => send<Named>(t, 'POST', '/categories', { name }),
  updateCategory: (t: string, id: string, body: { name?: string; is_active?: boolean }) => send<Named>(t, 'PATCH', `/categories/${id}`, body),
  brands: (t: string, s?: AbortSignal) => get<Named[]>(t, '/brands', undefined, s),
  createBrand: (t: string, name: string) => send<Named>(t, 'POST', '/brands', { name }),
  updateBrand: (t: string, id: string, body: { name?: string; is_active?: boolean }) => send<Named>(t, 'PATCH', `/brands/${id}`, body),

  products: (t: string, p: Params, s?: AbortSignal) => get<Paged<ProductRow> & { low_stock: number }>(t, '/products', p, s),
  product: (t: string, id: string, s?: AbortSignal) => get<ProductDetail>(t, `/products/${id}`, undefined, s),
  createProduct: (t: string, body: unknown) => send<{ id: string }>(t, 'POST', '/products', body),
  updateProduct: (t: string, id: string, body: unknown) => send<ProductDetail>(t, 'PATCH', `/products/${id}`, body),
  setPrice: (t: string, body: { product_id: string; retailer_id: string | null; dealer_price: string; price_basis: PriceBasis; tax_inclusive: boolean }) =>
    send<Price>(t, 'PUT', '/prices', body),
  removePrice: (t: string, productId: string, retailerId: string) =>
    send<object>(t, 'DELETE', '/prices', undefined, { product_id: productId, retailer_id: retailerId }),

  schemes: (t: string, p: Params, s?: AbortSignal) => get<Paged<SchemeRow>>(t, '/schemes', p, s),
  createSchemes: (t: string, body: unknown) => send<SchemeRow[]>(t, 'POST', '/schemes', body),
  updateScheme: (t: string, id: string, body: unknown) => send<SchemeRow>(t, 'PATCH', `/schemes/${id}`, body),

  stock: (t: string, p: Params, s?: AbortSignal) => get<Paged<ProductRow> & { low_stock: number }>(t, '/stock', p, s),
  adjustStock: (t: string, productId: string, body: { mode: 'add' | 'remove' | 'set'; quantity: string; reason: string }) =>
    send<{ change: string; stock_before: string; stock_after: string }>(t, 'POST', `/stock/${productId}/adjust`, body),
  stockHistory: (t: string, productId: string, s?: AbortSignal) => get<Movement[]>(t, `/stock/${productId}/history`, undefined, s),

  reportList: (t: string, s?: AbortSignal) => get<{ name: string; title: string; uses_dates: boolean }[]>(t, '/reports', undefined, s),
  report: (t: string, name: string, p: Params, s?: AbortSignal) => get<Report>(t, `/reports/${name}`, p, s),
  reportCsv: (t: string, name: string, p: { from_date?: string; to_date?: string }) => apiDownload(`/admin/reports/${name}/csv`, t, p),
}

/** ADMIN: upload or replace a product image (JPEG/PNG/WebP, max 5 MB). */
export async function uploadProductImage(token: string, productId: string, file: File): Promise<void> {
  const body = new FormData()
  body.append('file', file)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/products/${productId}/image`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
  } catch {
    throw new ApiError('Cannot reach the DukaanFlow server. Check your connection and try again.', 0, 'NETWORK_ERROR')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(payload?.message ?? `Upload failed (HTTP ${response.status})`, response.status, payload?.error_code ?? 'UNKNOWN_ERROR', payload?.details ?? {})
  }
}
