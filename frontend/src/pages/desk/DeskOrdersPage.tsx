import { useCallback, useState } from 'react'
import { ApiError } from '../../api/client'
import { exportToTally, fetchSalesmen, listDeskOrders, type DeskView } from '../../api/orderDesk'
import type { OrderSource, OrderStatus } from '../../api/orders'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { Icon } from '../../components/Icon'
import { Button, Empty, ErrorBox, Loading, Notice } from '../../components/ui'
import { EMPTY_FILTERS, saveBlob, type FilterState } from './deskFormat'
import { Filters, OrderTable, PageHeader, Pager, type Column } from './deskUi'

const LIMIT = 20

export type Section = 'incoming' | 'confirmed' | 'rejected' | 'clarification' | 'history'

const SECTIONS: Record<Section, {
  view: DeskView
  title: string
  subtitle: string
  statuses?: OrderStatus[]
  columns: Column[]
  hint?: string
  dateLabel?: string
  empty: string
}> = {
  incoming: {
    view: 'incoming',
    title: 'Incoming orders',
    subtitle: 'Every new order waits here: retailer app, salesman app and AI capture. Accept or reject each one.',
    statuses: ['PENDING', 'CREDIT_HOLD', 'ON_HOLD'],
    columns: ['retailer', 'placed', 'amount', 'source', 'salesman', 'status', 'warnings', 'review'],
    hint: 'Each order below is waiting for you. Click Review to check it, then Accept or Reject it.',
    empty: 'No orders are waiting for review.',
  },
  clarification: {
    view: 'clarification',
    title: 'Clarification required',
    subtitle: 'Orders the desk has asked the retailer or salesman about. They are kept exactly as placed.',
    columns: ['retailer', 'source', 'amount', 'reason', 'last_action', 'warnings', 'review'],
    hint: 'You asked about these orders. When you have the answer, click Review to Accept, Edit or Reject.',
    empty: 'No orders are waiting for a clarification.',
  },
  confirmed: {
    view: 'confirmed',
    title: 'Confirmed orders',
    subtitle: 'Stock deducted and credit debited. Export them to Tally and prepare dispatch.',
    columns: ['retailer', 'amount', 'source', 'salesman', 'confirmed', 'tally'],
    dateLabel: 'Confirmed',
    empty: 'No confirmed orders match.',
  },
  rejected: {
    view: 'rejected',
    title: 'Rejected orders',
    subtitle: 'The retailer and salesman see the rejection reason on the order.',
    columns: ['retailer', 'source', 'amount', 'reason', 'last_action'],
    empty: 'No rejected orders match.',
  },
  history: {
    view: 'all',
    title: 'Order history',
    subtitle: 'Every order with its latest action. Open an order for its full history.',
    statuses: ['PENDING', 'CREDIT_HOLD', 'ON_HOLD', 'CLARIFICATION_REQUIRED', 'APPROVED', 'REJECTED'],
    columns: ['retailer', 'placed', 'amount', 'source', 'status', 'last_action'],
    empty: 'No orders match.',
  },
}

export function DeskOrdersPage({ section }: { section: Section }) {
  const config = SECTIONS[section]
  // ?salesman=<id> pre-filters (links from the admin's salesman page).
  const [filters, setFiltersState] = useState<FilterState>(() => ({ ...EMPTY_FILTERS, salesman: new URLSearchParams(window.location.search).get('salesman') ?? '' }))
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [exportMessage, setExportMessage] = useState<{ tone: 'success' | 'warn'; text: string } | null>(null)
  const setFilters = useCallback((f: FilterState) => {
    setFiltersState(f)
    setPage(1)
    setSelected(new Set())
  }, [])

  const salesmen = useLoad((t, s) => fetchSalesmen(t, s), 'salesmen')
  const key = JSON.stringify([config.view, filters, page])
  const orders = useLoad((t, s) => listDeskOrders(t, {
    view: config.view,
    status: filters.status ? [filters.status as OrderStatus] : undefined,
    source: (filters.source || undefined) as OrderSource | undefined,
    search: filters.search || undefined,
    salesman_id: filters.salesman || undefined,
    from_date: filters.from || undefined,
    to_date: filters.to || undefined,
    exported: filters.exported === '' ? undefined : filters.exported === 'true',
    sort: filters.sort,
    page,
    limit: LIMIT,
  }, s), key)

  const rows = orders.state.status === 'ready' ? orders.state.data.items : []
  const toggle = (id: string) => setSelected((s) => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const toggleAll = () => setSelected((s) => (rows.every((r) => s.has(r.id)) ? new Set() : new Set(rows.map((r) => r.id))))

  return (
    <>
      <PageHeader title={config.title} subtitle={config.subtitle}
        actions={section === 'confirmed' ? <TallyExport selected={[...selected]} filters={filters} onMessage={setExportMessage} onDone={() => { setSelected(new Set()); orders.reload() }} /> : undefined} />
      {exportMessage && <div className="mt-3"><Notice tone={exportMessage.tone}>{exportMessage.text}</Notice></div>}
      {config.hint && <p className="mt-3 rounded-xl bg-leaf-50 px-4 py-3 text-sm font-semibold text-leaf-900">{config.hint}</p>}
      <Filters value={filters} onChange={setFilters} statuses={config.statuses} dateLabel={config.dateLabel}
        salesmen={salesmen.state.status === 'ready' ? salesmen.state.data : []} showExported={section === 'confirmed'} />
      <div className="mt-4">
        {orders.state.status === 'error' ? (
          <ErrorBox message={orders.state.message} onRetry={orders.reload} />
        ) : orders.state.status === 'loading' ? (
          <Loading label="Loading orders…" />
        ) : rows.length === 0 ? (
          <Empty title="Nothing here">{JSON.stringify({ ...filters, sort: 'newest' }) === JSON.stringify(EMPTY_FILTERS) ? config.empty : 'Try other filters.'}</Empty>
        ) : (
          <>
            <OrderTable rows={rows} columns={config.columns} faded={orders.loading}
              {...(section === 'confirmed' ? { selected, onToggle: toggle, onToggleAll: toggleAll } : {})} />
            <Pager page={page} total={orders.state.data.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </div>
    </>
  )
}

/** Tally export from the Confirmed section. Already exported orders are skipped, so a second
 *  click cannot export them twice; re-exporting is a separate, explicit choice. */
function TallyExport({ selected, filters, onDone, onMessage: setMessage }: {
  selected: string[]
  filters: FilterState
  onDone: () => void
  onMessage: (m: { tone: 'success' | 'warn'; text: string } | null) => void
}) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [busy, setBusy] = useState(false)
  const [reExport, setReExport] = useState(false)

  async function run() {
    setBusy(true)
    setMessage(null)
    try {
      const body = selected.length
        ? { order_ids: selected, include_exported: reExport }
        : { from_date: filters.from || undefined, to_date: filters.to || undefined, include_exported: reExport }
      const { blob, filename, count } = await exportToTally(token, body)
      saveBlob(blob, filename)
      setMessage({ tone: 'success', text: `${count} ${count === 1 ? 'order' : 'orders'} exported to ${filename} and marked as exported.` })
      setReExport(false)
      onDone()
    } catch (err) {
      const nothing = err instanceof ApiError && err.code === 'NOTHING_TO_EXPORT'
      setMessage({ tone: 'warn', text: toMessage(err) + (nothing && !reExport ? '. Tick “Export again” to re-export them.' : '') })
    } finally {
      setBusy(false)
    }
  }

  const scope = selected.length
    ? `${selected.length} selected`
    : filters.from || filters.to ? 'confirmed in the chosen dates' : 'all not yet exported'
  return (
    <div className="flex flex-wrap items-center justify-end gap-3">
        <label className="flex items-center gap-2 text-sm font-semibold text-ink-soft">
          <input type="checkbox" checked={reExport} onChange={(e) => setReExport(e.target.checked)} className="h-4 w-4 accent-leaf-700" />
          Export again
        </label>
      <Button busy={busy} onClick={run}><Icon name="download" className="h-4 w-4" /> Export to Tally ({scope})</Button>
    </div>
  )
}
