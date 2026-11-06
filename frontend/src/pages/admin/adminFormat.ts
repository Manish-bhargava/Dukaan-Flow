import type { AuditEntry } from '../../api/admin'
import { rupees } from '../../format'

/** Labels for audit actions (master data) and order history (prefixed ORDER_). */
export const ACTION_LABELS: Record<string, string> = {
  RETAILER_CREATED: 'Retailer created', RETAILER_UPDATED: 'Retailer edited', RETAILER_ACTIVATED: 'Retailer activated',
  RETAILER_DEACTIVATED: 'Retailer deactivated', ASSIGNMENT_CHANGED: 'Salesman assignment changed',
  CREDIT_LIMIT_CHANGED: 'Credit limit changed', ORDERING_RESTRICTED: 'Ordering paused', ORDERING_RESTORED: 'Ordering allowed again',
  USER_CREATED: 'User created', USER_UPDATED: 'User edited', USER_ROLE_CHANGED: 'Role changed', USER_ACTIVATED: 'User activated',
  USER_DEACTIVATED: 'User deactivated', PASSWORD_RESET: 'Password reset',
  CATEGORY_CREATED: 'Category created', CATEGORY_UPDATED: 'Category changed', BRAND_CREATED: 'Brand created', BRAND_UPDATED: 'Brand changed',
  PRODUCT_CREATED: 'Product created', PRODUCT_UPDATED: 'Product edited', PRODUCT_ACTIVATED: 'Product activated',
  PRODUCT_DEACTIVATED: 'Product deactivated', PRODUCT_IMAGE_CHANGED: 'Product image changed',
  PRICE_CHANGED: 'Price changed', PRICE_REMOVED: 'Retailer price removed',
  SCHEME_CREATED: 'Scheme created', SCHEME_UPDATED: 'Scheme changed', STOCK_CHANGED: 'Stock changed',
  SETTINGS_CHANGED: 'Settings changed', SYNC_FAILED: 'Salesman sync failed',
  ORDER_RECEIVED: 'Order received', ORDER_CONFIRMED: 'Order confirmed', ORDER_REJECTED: 'Order rejected',
  ORDER_CORRECTED: 'Order edited (line corrected)', ORDER_CLARIFICATION_REQUESTED: 'Clarification requested',
  ORDER_PUT_ON_HOLD: 'Order put on hold', ORDER_CREDIT_HOLD: 'Order moved to credit hold', ORDER_EXPORTED: 'Exported to Tally',
}

export const ENTITY_LABELS: Record<string, string> = {
  retailer: 'Retailer', credit: 'Credit', user: 'User', category: 'Category', brand: 'Brand', product: 'Product',
  price: 'Price', scheme: 'Scheme', stock: 'Stock', settings: 'Settings', order: 'Order', order_sync: 'Salesman sync',
}

const MONEY_FIELDS = new Set(['credit_limit', 'dealer_price'])

function show(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (MONEY_FIELDS.has(field) && !Number.isNaN(Number(value))) return rupees(String(value))
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) return new Date(value).toLocaleString('en-IN')
  return String(value)
}

/** One readable line for an audit entry's details. */
export function describeChange(e: AuditEntry): string {
  const d = (e.details ?? {}) as Record<string, unknown>
  if (d.changes && typeof d.changes === 'object') {
    return Object.entries(d.changes as Record<string, { from?: unknown; to?: unknown }>)
      .filter(([k]) => k !== 'salesman_id')
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${show(k, v.from)} → ${show(k, v.to)}`).join(' · ')
  }
  if (e.action === 'PRICE_CHANGED' || e.action === 'PRICE_REMOVED') {
    const from = d.from as Record<string, unknown> | null
    const to = d.to as Record<string, unknown> | undefined
    return `${d.scope}: ${from ? show('dealer_price', from.dealer_price) : 'none'} → ${to ? `${show('dealer_price', to.dealer_price)} / ${String(to.price_basis).toLowerCase()}` : 'removed'}`
  }
  if (e.action === 'STOCK_CHANGED') return `${show('', d.previous)} → ${show('', d.new)} cases · ${d.reason ?? ''}`
  if (e.action === 'SYNC_FAILED') return `${d.message ?? d.error_code}`
  if (e.action === 'ORDERING_RESTRICTED' || e.action === 'ORDERING_RESTORED') return String(d.reason ?? d.previous_reason ?? '')
  if (d.after && typeof d.after === 'object') {
    return Object.entries(d.after as Record<string, unknown>).filter(([k]) => !k.endsWith('_id'))
      .slice(0, 5).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${show(k, v)}`).join(' · ')
  }
  if (e.entity_type === 'order') {
    const old = d.old as Record<string, string> | undefined
    const next = d.new as Record<string, string> | undefined
    if (old && next) return `${old.sku}: ${Number(old.quantity)} → ${Number(next.quantity)} cases`
  }
  return e.message ?? ''
}

export const SCHEME_STATE_TONE = { active: 'green', upcoming: 'blue', expired: 'gray', inactive: 'gray' } as const

export const todayIst = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
export const daysAgoIst = (n: number) => new Date(Date.now() - n * 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
