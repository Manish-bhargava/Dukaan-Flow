import type { DeskSort, OrderEvent } from '../../api/orderDesk'
import { dateTime } from '../../format'

/** Order Desk constants and helpers (non-component exports of the desk screens). */

export const EVENT_LABELS: Record<OrderEvent['action'], string> = {
  RECEIVED: 'Order received',
  CONFIRMED: 'Confirmed',
  CREDIT_HOLD: 'Moved to credit hold',
  PUT_ON_HOLD: 'Put on hold',
  CLARIFICATION_REQUESTED: 'Clarification requested',
  CORRECTED: 'Line corrected',
  REJECTED: 'Rejected',
  EXPORTED: 'Exported to Tally',
}

export function eventSummary(e: OrderEvent): string {
  const who = e.actor ? `${e.actor.name}` : 'not recorded'
  return `${EVENT_LABELS[e.action]} · ${who} · ${dateTime(e.created_at)}`
}

export interface FilterState {
  search: string
  from: string
  to: string
  status: string
  source: string
  salesman: string
  sort: DeskSort
  exported: string
}

export const EMPTY_FILTERS: FilterState = { search: '', from: '', to: '', status: '', source: '', salesman: '', sort: 'newest', exported: '' }

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Freed a moment later: revoking at once can cut the download short in some browsers.
  window.setTimeout(() => URL.revokeObjectURL(url), 30000)
}
