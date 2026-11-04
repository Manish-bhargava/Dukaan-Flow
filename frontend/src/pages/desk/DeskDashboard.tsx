import { useEffect, useState } from 'react'
import { downloadTallyCsv, fetchDeskSummary, listOrders, type OrderSource, type OrderStatus } from '../../api/orders'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, Empty, ErrorBox, Loading, SourceBadge, StatusBadge } from '../../components/ui'
import { dateTime, rupees } from '../../format'

const PAGE_SIZE = 20
const VIEWS: { id: string; label: string; statuses: OrderStatus[] }[] = [
  { id: 'review', label: 'Needs review', statuses: ['PENDING', 'CREDIT_HOLD', 'ON_HOLD'] },
  { id: 'PENDING', label: 'Submitted', statuses: ['PENDING'] },
  { id: 'CREDIT_HOLD', label: 'Credit hold', statuses: ['CREDIT_HOLD'] },
  { id: 'ON_HOLD', label: 'On hold', statuses: ['ON_HOLD'] },
  { id: 'APPROVED', label: 'Confirmed', statuses: ['APPROVED'] },
  { id: 'REJECTED', label: 'Rejected', statuses: ['REJECTED'] },
  { id: 'all', label: 'All', statuses: [] },
]

export function DeskDashboard() {
  const [view, setView] = useState('review')
  const [source, setSource] = useState<OrderSource | ''>('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const statuses = VIEWS.find((v) => v.id === view)!.statuses
  const summary = useLoad((t, s) => fetchDeskSummary(t, s), 'summary')
  const orders = useLoad(
    (t, s) => listOrders(t, { status: statuses, source: source || undefined, search, page, limit: PAGE_SIZE }, s),
    `${view}|${source}|${search}|${page}`,
  )
  const counts = summary.state.status === 'ready' ? summary.state.data : null
  const countFor = (statuses: OrderStatus[]) =>
    counts && statuses.length ? statuses.reduce((sum, s) => sum + (counts[s] ?? 0), 0) : null

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-extrabold text-ink">Orders</h1>
        <TallyExport />
      </div>

      <div className="-mx-4 mt-4 flex overflow-x-auto border-b border-gray-200 px-4 sm:mx-0 sm:px-0" role="tablist">
        {VIEWS.map((v) => {
          const count = countFor(v.statuses)
          return (
            <button
              key={v.id}
              type="button"
              role="tab"
              aria-selected={view === v.id}
              onClick={() => {
                setView(v.id)
                setPage(1)
              }}
              className={`flex min-h-12 shrink-0 items-center gap-1.5 border-b-2 px-3 text-sm font-bold ${
                view === v.id ? 'border-leaf-700 text-leaf-800' : 'border-transparent text-ink-soft hover:text-leaf-700'
              }`}
            >
              {v.label}
              {count !== null && <span className="rounded-full bg-gray-100 px-1.5 text-xs text-ink-soft">{count}</span>}
            </button>
          )
        })}
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search order number or shop"
          aria-label="Search orders"
          className="min-h-11 flex-1 rounded-lg border border-gray-300 px-3 text-base outline-none focus:border-leaf-600"
        />
        <select
          value={source}
          onChange={(e) => {
            setSource(e.target.value as OrderSource | '')
            setPage(1)
          }}
          aria-label="Order source"
          className="min-h-11 rounded-lg border border-gray-300 bg-white px-3 text-base"
        >
          <option value="">All sources</option>
          <option value="AI">AI text</option>
          <option value="MANUAL">Manual</option>
          <option value="SALESMAN">Salesman</option>
        </select>
      </div>

      <div className="mt-3">
        {orders.state.status === 'error' ? (
          <ErrorBox message={orders.state.message} onRetry={orders.reload} />
        ) : orders.state.status === 'loading' ? (
          <Loading label="Loading orders…" />
        ) : orders.state.data.items.length === 0 ? (
          <Empty title="No orders here">{search || source ? 'Try another search or filter.' : 'New orders appear here as retailers place them.'}</Empty>
        ) : (
          <>
            <div className={`overflow-x-auto ${orders.loading ? 'opacity-60' : ''}`}>
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-gray-200 text-xs uppercase text-ink-soft">
                  <tr>
                    <th className="py-2 pr-3">Order</th>
                    <th className="py-2 pr-3">Retailer</th>
                    <th className="py-2 pr-3">Source</th>
                    <th className="py-2 pr-3 text-right">Items</th>
                    <th className="py-2 pr-3 text-right">Total</th>
                    <th className="py-2 pr-3">Placed</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {orders.state.data.items.map((o) => (
                    <tr key={o.id} className="hover:bg-gray-50">
                      <td className="py-3 pr-3">
                        <Link to={`/desk/orders/${o.id}`} className="font-bold text-leaf-700 underline-offset-2 hover:underline">
                          {o.order_number}
                        </Link>
                      </td>
                      <td className="py-3 pr-3">
                        <span className="font-semibold text-ink">{o.retailer.shop_name}</span>
                        <span className="block text-xs text-ink-soft">{o.retailer.city}</span>
                      </td>
                      <td className="py-3 pr-3"><SourceBadge source={o.source} /></td>
                      <td className="py-3 pr-3 text-right">{o.item_count}</td>
                      <td className="py-3 pr-3 text-right font-bold">{rupees(o.grand_total)}</td>
                      <td className="py-3 pr-3 text-ink-soft">{dateTime(o.created_at)}</td>
                      <td className="py-3"><StatusBadge status={o.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={page} total={orders.state.data.total} onPage={setPage} />
          </>
        )}
      </div>
    </>
  )
}

function Pager({ page, total, onPage }: { page: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  if (pages === 1) return <p className="mt-3 text-xs text-ink-soft">{total} orders</p>
  return (
    <div className="mt-3 flex items-center justify-between gap-3 text-sm">
      <span className="text-ink-soft">
        Page {page} of {pages} · {total} orders
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  )
}

function TallyExport() {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function download() {
    setBusy(true)
    setError('')
    try {
      const { blob, filename } = await downloadTallyCsv(token, from || undefined, to || undefined)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(toMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-xs font-bold text-ink-soft">
        Confirmed from
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="mt-1 block min-h-11 rounded-lg border border-gray-300 px-2 text-sm text-ink" />
      </label>
      <label className="text-xs font-bold text-ink-soft">
        to
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="mt-1 block min-h-11 rounded-lg border border-gray-300 px-2 text-sm text-ink" />
      </label>
      <Button variant="secondary" busy={busy} onClick={download}>Export Tally CSV</Button>
      {error && <p className="w-full text-sm text-red-700">{error}</p>}
    </div>
  )
}
