import { useState } from 'react'
import { fetchOverview, listDeskOrders } from '../../api/orderDesk'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Empty, ErrorBox, Loading } from '../../components/ui'
import { OrderTable, PageHeader, StatCard } from './deskUi'

/** Order Desk overview: today's numbers and the open orders that need attention first. */
export function DeskOverview() {
  const [today] = useState(() => new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }))
  const overview = useLoad((t, s) => fetchOverview(t, s), 'overview')
  const incoming = useLoad((t, s) => listDeskOrders(t, { view: 'incoming', sort: 'oldest', limit: 50 }, s), 'overview-incoming')

  if (overview.state.status === 'error') return <ErrorBox message={overview.state.message} onRetry={overview.reload} />
  if (overview.state.status === 'loading') return <Loading label="Loading overview…" />
  const o = overview.state.data
  const attention = incoming.state.status === 'ready' ? incoming.state.data.items.filter((r) => r.warnings.length > 0).slice(0, 6) : []

  return (
    <>
      <PageHeader title="Overview" subtitle={today} />
      <section className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border-2 border-leaf-200 bg-leaf-50 p-4">
        <div>
          <p className="text-lg font-extrabold text-leaf-900">
            {o.pending_review ? `${o.pending_review} ${o.pending_review === 1 ? 'order is' : 'orders are'} waiting for your decision` : 'No orders are waiting right now'}
          </p>
          <p className="text-sm text-ink">Open each order, check it, then Accept or Reject it. New orders from retailers, salesmen and AI messages all arrive in Incoming.</p>
        </div>
        {o.pending_review > 0 && (
          <Link to="/desk/incoming" className="inline-flex min-h-12 items-center rounded-xl bg-leaf-700 px-5 font-bold text-white hover:bg-leaf-800">Start reviewing →</Link>
        )}
      </section>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard icon="inbox" label="Orders received today" value={o.received_today} hint="From all sources" to="/desk/history" />
        <StatCard icon="clock" label="Pending review" value={o.pending_review} hint="Waiting for a decision" to="/desk/incoming" tone={o.pending_review ? 'warn' : 'plain'} />
        <StatCard icon="help" label="Awaiting clarification" value={o.awaiting_clarification} hint="Asked the retailer or salesman" to="/desk/clarification" tone={o.awaiting_clarification ? 'warn' : 'plain'} />
        <StatCard icon="checkCircle" label="Confirmed today" value={o.confirmed_today} hint={`${o.confirmed_total} confirmed in total · ${o.not_exported} not yet in Tally`} to="/desk/confirmed" tone="good" />
        <StatCard icon="xCircle" label="Rejected today" value={o.rejected_today} hint={`${o.rejected_total} rejected in total`} to="/desk/rejected" />
        <StatCard icon="alert" label="Stock or credit issues" value={o.with_stock_or_credit_issues} hint="Open orders that cannot be confirmed as they are" to="/desk/incoming" tone={o.with_stock_or_credit_issues ? 'warn' : 'plain'} />
      </div>

      <section className="mt-8">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-extrabold text-ink">Needs attention</h2>
            <p className="text-sm text-ink-soft">Oldest incoming orders with a warning.</p>
          </div>
          <Link to="/desk/incoming" className="text-sm font-bold text-leaf-700">All incoming →</Link>
        </div>
        <div className="mt-3">
          {incoming.state.status === 'error' ? <ErrorBox message={incoming.state.message} onRetry={incoming.reload} />
            : incoming.state.status === 'loading' ? <Loading />
            : attention.length === 0 ? <Empty title="Nothing needs attention">No incoming order has a stock, credit or data warning.</Empty>
            : <OrderTable rows={attention} columns={['retailer', 'placed', 'amount', 'source', 'status', 'warnings']} />}
        </div>
      </section>
    </>
  )
}
