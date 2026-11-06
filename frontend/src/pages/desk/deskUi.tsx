import { useEffect, useState, type ReactNode } from 'react'
import type { DeskOrderRow, DeskSort, DeskWarning, OrderEvent, Person } from '../../api/orderDesk'
import { EMPTY_FILTERS, EVENT_LABELS, eventSummary, type FilterState } from './deskFormat'
import type { OrderSource, OrderStatus } from '../../api/orders'
import { Link } from '../../components/Link'
import { Icon, type IconName } from '../../components/Icon'
import { Button, SourceBadge, StatusBadge } from '../../components/ui'
import { dateTime, rupees, SOURCE_LABELS, STATUS_LABELS } from '../../format'

/** Shared Order Desk building blocks (lists, filters, warnings, history). */

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-extrabold text-ink sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-soft">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-end gap-2 print:hidden">{actions}</div>}
    </div>
  )
}

export function StatCard({ label, value, hint, icon, to, tone = 'plain' }: {
  label: string; value: number | string; hint?: string; icon: IconName; to?: string; tone?: 'plain' | 'warn' | 'good'
}) {
  const tones = {
    plain: 'bg-leaf-50 text-leaf-700',
    warn: 'bg-mango-100 text-mango-600',
    good: 'bg-leaf-100 text-leaf-800',
  }[tone]
  const body = (
    <>
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tones}`}><Icon name={icon} /></span>
      <span className="min-w-0">
        <span className="block text-2xl font-extrabold leading-tight text-ink">{value}</span>
        <span className="block text-sm font-semibold text-ink">{label}</span>
        {hint && <span className="block text-xs text-ink-soft">{hint}</span>}
      </span>
    </>
  )
  const cls = 'flex items-start gap-3 rounded-2xl border border-gray-200 bg-white p-4'
  return to ? <Link to={to} className={`${cls} transition-colors hover:border-leaf-300 hover:bg-leaf-50/40`}>{body}</Link> : <div className={cls}>{body}</div>
}

export function WarningChips({ warnings }: { warnings: DeskWarning[] }) {
  if (warnings.length === 0) return null
  const errors = warnings.filter((w) => w.severity === 'error').length
  const label = warnings.length === 1 ? WARNING_SHORT[warnings[0].code] ?? 'Check order' : `${warnings.length} issues`
  return (
    <span title={warnings.map((w) => w.message).join('\n')}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${errors ? 'bg-red-50 text-red-700' : 'bg-mango-100 text-mango-600'}`}>
      <Icon name="alert" className="h-3.5 w-3.5" /> {label}
    </span>
  )
}

const WARNING_SHORT: Record<string, string> = {
  INSUFFICIENT_STOCK: 'Low stock',
  CREDIT_LIMIT_EXCEEDED: 'Over credit',
  PRICE_CHANGED: 'Price changed',
  SCHEME_CHANGED: 'Scheme changed',
  PRODUCT_INACTIVE: 'Inactive product',
  PRICE_NOT_AVAILABLE: 'No price',
  OFFLINE_DATA_CHANGED: 'Offline changes',
  AI_MATCH_UNCERTAIN: 'AI unsure',
  POSSIBLE_DUPLICATE: 'Possible duplicate',
}

export function WarningList({ warnings }: { warnings: DeskWarning[] }) {
  if (warnings.length === 0) return null
  return (
    <section role="alert" className="rounded-2xl border border-mango-200 bg-mango-100/50 p-4">
      <h2 className="flex items-center gap-2 font-extrabold text-leaf-950"><Icon name="alert" className="h-5 w-5 text-mango-600" /> Check before deciding</h2>
      <ul className="mt-2 space-y-1.5 text-sm">
        {warnings.map((w, i) => (
          <li key={i} className="flex gap-2">
            <span className={`mt-0.5 shrink-0 rounded px-1.5 text-[11px] font-bold uppercase ${w.severity === 'error' ? 'bg-red-100 text-red-700' : 'bg-white text-mango-600'}`}>
              {WARNING_SHORT[w.code] ?? w.code}
            </span>
            <span className="text-ink">{w.message}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function History({ events }: { events: OrderEvent[] }) {
  return (
    <ol className="relative space-y-4 border-l-2 border-leaf-100 pl-5">
      {events.map((e, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-leaf-600 ring-2 ring-leaf-100" />
          <p className="text-sm font-bold text-ink">{EVENT_LABELS[e.action]}</p>
          <p className="text-xs text-ink-soft">
            {dateTime(e.created_at)} · {e.actor ? `${e.actor.name} (${roleLabel(e.actor.role)})` : 'user not recorded'}
          </p>
          {e.message && <p className="mt-1 text-sm text-ink">{e.message}</p>}
          <EventDetails event={e} />
        </li>
      ))}
    </ol>
  )
}

function roleLabel(role: string) {
  return { RETAILER: 'retailer', SALESMAN: 'salesman', ORDER_DESK: 'order desk', ADMIN: 'admin' }[role] ?? role
}

function EventDetails({ event }: { event: OrderEvent }) {
  const d = event.details ?? {}
  if (event.action === 'CORRECTED' && d.old && d.new) {
    const old = d.old as Record<string, string>
    const next = d.new as Record<string, string>
    return (
      <p className="mt-1 text-xs text-ink-soft">
        {old.sku === next.sku ? old.sku : `${old.sku} → ${next.sku}`}: {Number(old.quantity)} → {Number(next.quantity)} cases ·
        order total {rupees(old.order_total)} → {rupees(next.order_total)}
      </p>
    )
  }
  if (event.action === 'RECEIVED' && typeof d.source === 'string') {
    return (
      <p className="mt-1 text-xs text-ink-soft">
        {SOURCE_LABELS[d.source as OrderSource] ?? d.source}
        {d.created_offline ? ' · created offline' : ''}
        {typeof d.status === 'string' ? ` · arrived as ${STATUS_LABELS[d.status as OrderStatus] ?? d.status}` : ''}
      </p>
    )
  }
  if (event.action === 'CONFIRMED' && d.credit_override) return <p className="mt-1 text-xs text-ink-soft">Released above the credit limit</p>
  return null
}

// ---------------------------------------------------------------- filters

const field = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 text-sm text-ink outline-none focus:border-leaf-600'

export function Filters({ value, onChange, statuses, salesmen, dateLabel = 'Placed', showExported = false }: {
  value: FilterState
  onChange: (f: FilterState) => void
  statuses?: OrderStatus[]
  salesmen: Person[]
  dateLabel?: string
  showExported?: boolean
}) {
  const [search, setSearch] = useState(value.search)
  useEffect(() => {
    if (search.trim() === value.search) return
    const timer = window.setTimeout(() => onChange({ ...value, search: search.trim() }), 300)
    return () => window.clearTimeout(timer)
  }, [search, value, onChange])
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch })
  const active = Object.entries(value).some(([k, v]) => k !== 'sort' && v !== '')

  return (
    <div className="mt-4 space-y-2 rounded-2xl border border-gray-200 bg-gray-50/60 p-3">
      <div className="relative">
        <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-soft" />
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search orders"
          placeholder="Search order ID, shop, owner or mobile number" className={`${field} w-full pl-10`} />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <label className="text-xs font-bold text-ink-soft">{dateLabel} from
          <input type="date" value={value.from} onChange={(e) => set({ from: e.target.value })} className={`${field} mt-1 block w-full`} />
        </label>
        <label className="text-xs font-bold text-ink-soft">to
          <input type="date" value={value.to} onChange={(e) => set({ to: e.target.value })} className={`${field} mt-1 block w-full`} />
        </label>
        {statuses && statuses.length > 1 && (
          <label className="text-xs font-bold text-ink-soft">Status
            <select value={value.status} onChange={(e) => set({ status: e.target.value })} className={`${field} mt-1 block w-full`}>
              <option value="">All</option>
              {statuses.map((s) => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
            </select>
          </label>
        )}
        <label className="text-xs font-bold text-ink-soft">Source
          <select value={value.source} onChange={(e) => set({ source: e.target.value })} className={`${field} mt-1 block w-full`}>
            <option value="">All sources</option>
            <option value="MANUAL">Retailer app</option>
            <option value="SALESMAN">Salesman app</option>
            <option value="AI">AI capture</option>
          </select>
        </label>
        <label className="text-xs font-bold text-ink-soft">Salesman
          <select value={value.salesman} onChange={(e) => set({ salesman: e.target.value })} className={`${field} mt-1 block w-full`}>
            <option value="">All salesmen</option>
            {salesmen.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        {showExported && (
          <label className="text-xs font-bold text-ink-soft">Tally
            <select value={value.exported} onChange={(e) => set({ exported: e.target.value })} className={`${field} mt-1 block w-full`}>
              <option value="">All</option>
              <option value="false">Not exported</option>
              <option value="true">Exported</option>
            </select>
          </label>
        )}
        <label className="text-xs font-bold text-ink-soft">Sort
          <select value={value.sort} onChange={(e) => set({ sort: e.target.value as DeskSort })} className={`${field} mt-1 block w-full`}>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="value_desc">Highest value</option>
            <option value="value_asc">Lowest value</option>
          </select>
        </label>
      </div>
      {active && (
        <button type="button" onClick={() => { setSearch(''); onChange({ ...EMPTY_FILTERS, sort: value.sort }) }}
          className="min-h-9 text-sm font-bold text-leaf-700 underline">Clear filters</button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- order list

export type Column = 'retailer' | 'placed' | 'amount' | 'source' | 'salesman' | 'status' | 'warnings' | 'reason' | 'last_action' | 'confirmed' | 'tally' | 'review'

const HEADERS: Record<Column, string> = {
  retailer: 'Retailer', placed: 'Placed', amount: 'Amount', source: 'Source', salesman: 'Salesman', status: 'Status',
  warnings: 'Checks', reason: 'Reason', last_action: 'Last action', confirmed: 'Confirmed', tally: 'Tally', review: '',
}

function cell(col: Column, o: DeskOrderRow): ReactNode {
  switch (col) {
    case 'retailer':
      return <><span className="font-semibold text-ink">{o.retailer.shop_name}</span><span className="block text-xs text-ink-soft">{o.retailer.owner_name} · {o.retailer.phone}</span></>
    case 'placed':
      return <span className="text-ink-soft">{dateTime(o.created_at)}{o.created_offline && <span className="block text-xs">created offline</span>}</span>
    case 'amount':
      return <span className="font-bold text-ink">{rupees(o.grand_total)}<span className="block text-xs font-normal text-ink-soft">{o.item_count} {o.item_count === 1 ? 'line' : 'lines'}</span></span>
    case 'source':
      return <SourceBadge source={o.source} />
    case 'salesman':
      return <span className="text-ink-soft">{o.salesman?.name ?? '—'}</span>
    case 'status':
      return <StatusBadge status={o.status} />
    case 'warnings':
      return o.warnings.length ? <WarningChips warnings={o.warnings} /> : <span className="text-xs font-semibold text-leaf-700">OK</span>
    case 'reason':
      return <span className="line-clamp-2 text-ink">{o.reason ?? '—'}</span>
    case 'last_action':
      return o.last_action ? <span className="text-xs text-ink-soft"><span className="block font-semibold text-ink">{EVENT_LABELS[o.last_action.action]}</span>{o.last_action.actor?.name ?? 'user not recorded'} · {dateTime(o.last_action.created_at)}</span> : '—'
    case 'confirmed':
      return o.approved_at ? <span className="text-ink-soft">{dateTime(o.approved_at)}<span className="block text-xs">{o.approved_by?.name ?? ''}</span></span> : '—'
    case 'review':
      return (
        <Link to={`/desk/orders/${o.id}`} className="inline-flex min-h-10 items-center whitespace-nowrap rounded-lg bg-leaf-700 px-3 text-sm font-bold text-white hover:bg-leaf-800">
          Review →
        </Link>
      )
    case 'tally':
      return o.tally_exported_at
        ? <span className="text-xs font-semibold text-leaf-700">Exported<span className="block font-normal text-ink-soft">{dateTime(o.tally_exported_at)}</span></span>
        : <span className="text-xs font-semibold text-mango-600">Not exported</span>
  }
}

const RIGHT: Column[] = ['amount']

/** Table on larger screens, cards on phones. */
export function OrderTable({ rows, columns, faded, selected, onToggle, onToggleAll }: {
  rows: DeskOrderRow[]
  columns: Column[]
  faded?: boolean
  selected?: Set<string>
  onToggle?: (id: string) => void
  onToggleAll?: () => void
}) {
  const selectable = Boolean(selected && onToggle)
  return (
    <div className={faded ? 'opacity-60' : ''}>
      <div className="hidden overflow-x-auto rounded-2xl border border-gray-200 md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-ink-soft">
            <tr>
              {selectable && (
                <th className="w-10 py-2.5 pl-4">
                  <input type="checkbox" aria-label="Select all" checked={rows.length > 0 && rows.every((r) => selected!.has(r.id))}
                    onChange={onToggleAll} className="h-4 w-4 accent-leaf-700" />
                </th>
              )}
              <th className="py-2.5 pl-4 pr-3">Order</th>
              {columns.map((c) => <th key={c} className={`py-2.5 pr-3 ${RIGHT.includes(c) ? 'text-right' : ''}`}>{HEADERS[c]}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((o) => (
              <tr key={o.id} className="align-top hover:bg-leaf-50/40">
                {selectable && (
                  <td className="py-3 pl-4">
                    <input type="checkbox" aria-label={`Select ${o.order_number}`} checked={selected!.has(o.id)} onChange={() => onToggle!(o.id)} className="h-4 w-4 accent-leaf-700" />
                  </td>
                )}
                <td className="py-3 pl-4 pr-3">
                  <Link to={`/desk/orders/${o.id}`} className="font-bold text-leaf-700 underline-offset-2 hover:underline">{o.order_number}</Link>
                </td>
                {columns.map((c) => <td key={c} className={`py-3 pr-3 ${RIGHT.includes(c) ? 'text-right' : ''}`}>{cell(c, o)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-2 md:hidden">
        {rows.map((o) => (
          <li key={o.id} className="flex gap-3 rounded-2xl border border-gray-200 bg-white p-3">
            {selectable && (
              <input type="checkbox" aria-label={`Select ${o.order_number}`} checked={selected!.has(o.id)} onChange={() => onToggle!(o.id)} className="mt-1 h-5 w-5 accent-leaf-700" />
            )}
            <Link to={`/desk/orders/${o.id}`} className="block min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-bold text-ink">{o.retailer.shop_name}</p>
                  <p className="text-xs text-ink-soft">{o.order_number} · {dateTime(o.created_at)}</p>
                </div>
                <p className="shrink-0 font-extrabold text-ink">{rupees(o.grand_total)}</p>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge status={o.status} />
                <SourceBadge source={o.source} />
                {o.salesman && <span className="text-xs text-ink-soft">· {o.salesman.name}</span>}
                <WarningChips warnings={o.warnings} />
                {columns.includes('tally') && cell('tally', o)}
              </div>
              {columns.includes('reason') && o.reason && <p className="mt-2 line-clamp-2 text-sm text-ink">{o.reason}</p>}
              {columns.includes('last_action') && o.last_action && <p className="mt-1 text-xs text-ink-soft">{eventSummary(o.last_action)}</p>}
              {columns.includes('review') && <span className="mt-3 flex min-h-11 items-center justify-center rounded-lg bg-leaf-700 text-sm font-bold text-white">Review and decide →</span>}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Pager({ page, total, limit, onPage }: { page: number; total: number; limit: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / limit))
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-ink-soft">{pages > 1 ? `Page ${page} of ${pages} · ` : ''}{total} {total === 1 ? 'order' : 'orders'}</span>
      {pages > 1 && (
        <div className="flex gap-2">
          <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
          <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
        </div>
      )}
    </div>
  )
}
