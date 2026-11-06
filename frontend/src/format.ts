import type { OrderSource, OrderStatus } from './api/orders'
import { t, word } from './i18n'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 })

/** Display a backend decimal string as rupees (display only, never used for calculation). */
export const rupees = (value: string | number) => inr.format(Number(value))

/** "25.000" -> "25" */
export const qty = (value: string | number) => Number(value).toLocaleString('en-IN', { maximumFractionDigits: 3 })

export const plural = (n: number | string, w: string) => `${qty(n)} ${word(w, Number(n))}`

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export const STATUS_LABELS: Record<OrderStatus, string> = {
  PENDING: t('Under review'),
  CREDIT_HOLD: t('Credit hold'),
  ON_HOLD: t('On hold'),
  CLARIFICATION_REQUIRED: t('Needs clarification'),
  APPROVED: t('Confirmed'),
  REJECTED: t('Rejected'),
}

export const STATUS_STYLES: Record<OrderStatus, string> = {
  PENDING: 'bg-sky-50 text-sky-800',
  CREDIT_HOLD: 'bg-orange-50 text-orange-800',
  ON_HOLD: 'bg-mango-100 text-mango-600',
  CLARIFICATION_REQUIRED: 'bg-cream-200 text-leaf-900',
  APPROVED: 'bg-leaf-50 text-leaf-700',
  REJECTED: 'bg-red-50 text-red-700',
}

export const SOURCE_LABELS: Record<OrderSource, string> = { MANUAL: 'Retailer app', AI: 'AI text', SALESMAN: 'Salesman app' }

/** How the retailer placed it, in their words. */
export const RETAILER_SOURCE_LABELS: Record<OrderSource, string> = { MANUAL: t('From catalogue'), AI: t('From message (AI)'), SALESMAN: t('By your salesman') }

export const gstLabel = (rate: string, taxInclusive: boolean | null) =>
  taxInclusive === null ? t('GST {rate}% (treatment not recorded)', { rate: qty(rate) })
    : t(taxInclusive ? 'incl. {rate}% GST' : '+ {rate}% GST', { rate: qty(rate) })

interface SchemeTerms {
  scheme_type: string
  min_quantity: string
  free_quantity: string
  discount_percentage: string
}

/** Plain-language offer, from the scheme's own terms (no calculation): "Buy 10 cases, get 1 free". */
export function offerHeadline(s: SchemeTerms, unit: string): string {
  const Units = `${unit.charAt(0).toUpperCase()}${unit.slice(1)}s`
  const hi = t('Buy {min} get {free} free') !== 'Buy {min} get {free} free'
  if (s.scheme_type === 'FREE_GOODS') {
    return hi ? t('Buy {min} get {free} free', { min: qty(s.min_quantity), free: qty(s.free_quantity), unit: word(unit, 2) })
      : `Buy ${qty(s.min_quantity)}, Get ${qty(s.free_quantity)} Free`
  }
  if (s.scheme_type === 'SLAB_DISCOUNT') {
    return hi ? t('{pct}% off on {min}+', { pct: qty(s.discount_percentage), min: qty(s.min_quantity), unit: word(unit, 2) })
      : `${qty(s.discount_percentage)}% Off on ${qty(s.min_quantity)}+ ${Units}`
  }
  return s.scheme_type
}

export function offerDetail(s: SchemeTerms, unit: string): string {
  if (s.scheme_type === 'FREE_GOODS') {
    return `For every ${plural(s.min_quantity, unit)} you order, you get ${plural(s.free_quantity, unit)} free. Free ${unit}s are added to your order automatically.`
  }
  if (s.scheme_type === 'SLAB_DISCOUNT') {
    return `Order ${qty(s.min_quantity)} or more ${unit}s and get ${qty(s.discount_percentage)}% off this product. The discount is applied automatically in your cart.`
  }
  return ''
}

/** Remaining credit as a share of the limit: green >= 50%, orange 20-50%, red < 20% (or none left). */
export function creditLevel(available: string | number, limit: string | number): 'high' | 'mid' | 'low' {
  const left = Number(available)
  const total = Number(limit)
  if (left <= 0 || total <= 0) return 'low'
  const share = left / total
  return share >= 0.5 ? 'high' : share >= 0.2 ? 'mid' : 'low'
}

export const CREDIT_LEVEL_STYLES: Record<'high' | 'mid' | 'low', { text: string; pill: string }> = {
  high: { text: 'text-leaf-700', pill: 'bg-leaf-50 text-leaf-700 ring-leaf-200' },
  mid: { text: 'text-orange-600', pill: 'bg-orange-50 text-orange-700 ring-orange-200' },
  low: { text: 'text-red-700', pill: 'bg-red-50 text-red-700 ring-red-200' },
}

export const CREDIT_EXPLANATION =
  'Credit lets you buy stock now and pay the distributor later. Orders from the catalogue are confirmed at once and added to ' +
  'your outstanding amount. Orders from a message hold their amount while the order desk reviews them: if rejected, the ' +
  'credit comes back. Payments you make reduce the outstanding amount. You can place orders up to the credit left.'

export const SYNC_LABELS: Record<'saved_offline' | 'pending_sync' | 'syncing' | 'synced' | 'sync_failed', string> = {
  saved_offline: 'Saved offline',
  pending_sync: 'Pending sync',
  syncing: 'Syncing…',
  synced: 'Synced',
  sync_failed: 'Sync failed',
}

export const SYNC_STYLES: Record<keyof typeof SYNC_LABELS, string> = {
  saved_offline: 'bg-gray-100 text-ink',
  pending_sync: 'bg-orange-50 text-orange-700',
  syncing: 'bg-sky-50 text-sky-800',
  synced: 'bg-leaf-50 text-leaf-700',
  sync_failed: 'bg-red-50 text-red-700',
}

/** "5 min ago", "2 h ago", or a date. */
export function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`
  return dateTime(iso)
}

export const isToday = (iso: string) => new Date(iso).toDateString() === new Date().toDateString()
