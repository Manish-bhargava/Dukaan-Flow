import type { OrderSource, OrderStatus } from './api/orders'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 })

/** Display a backend decimal string as rupees (display only, never used for calculation). */
export const rupees = (value: string | number) => inr.format(Number(value))

/** "25.000" -> "25" */
export const qty = (value: string | number) => Number(value).toLocaleString('en-IN', { maximumFractionDigits: 3 })

export const plural = (n: number | string, word: string) => `${qty(n)} ${word}${Number(n) === 1 ? '' : 's'}`

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })

export const STATUS_LABELS: Record<OrderStatus, string> = {
  PENDING: 'Submitted',
  CREDIT_HOLD: 'Credit hold',
  ON_HOLD: 'On hold',
  APPROVED: 'Confirmed',
  REJECTED: 'Rejected',
}

export const STATUS_STYLES: Record<OrderStatus, string> = {
  PENDING: 'bg-sky-50 text-sky-800',
  CREDIT_HOLD: 'bg-orange-50 text-orange-800',
  ON_HOLD: 'bg-mango-100 text-mango-600',
  APPROVED: 'bg-leaf-50 text-leaf-700',
  REJECTED: 'bg-red-50 text-red-700',
}

export const SOURCE_LABELS: Record<OrderSource, string> = { MANUAL: 'Manual', AI: 'AI text', SALESMAN: 'Salesman' }

export const gstLabel = (rate: string, taxInclusive: boolean | null) =>
  taxInclusive === null ? `GST ${qty(rate)}% (treatment not recorded)` : `${taxInclusive ? 'incl.' : '+'} ${qty(rate)}% GST`

interface SchemeTerms {
  scheme_type: string
  min_quantity: string
  free_quantity: string
  discount_percentage: string
}

/** Plain-language offer, from the scheme's own terms (no calculation): "Buy 10 cases, get 1 free". */
export function offerHeadline(s: SchemeTerms, unit: string): string {
  const Units = `${unit.charAt(0).toUpperCase()}${unit.slice(1)}s`
  if (s.scheme_type === 'FREE_GOODS') return `Buy ${qty(s.min_quantity)}, Get ${qty(s.free_quantity)} Free`
  if (s.scheme_type === 'SLAB_DISCOUNT') return `${qty(s.discount_percentage)}% Off on ${qty(s.min_quantity)}+ ${Units}`
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
