import { useState } from 'react'
import { admin } from '../../api/admin'
import { ROLE_LABELS } from '../../api/auth'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Notice, StatusBadge } from '../../components/ui'
import { dateTime, qty, rupees, STATUS_LABELS } from '../../format'
import { Pager } from '../desk/deskUi'
import { ACTION_LABELS, describeChange } from './adminFormat'
import { AdminPage, Card, DataTable, Loaded, Pill, Stat, Tabs } from './adminUi'
import { SyncBadge } from './SalesmanPages'

/** Order Desk oversight: the desk's queue, issues, corrections, exports and who did what. */
export function OrderDeskOversightPage() {
  const data = useLoad((t, s) => admin.orderDesk(t, s), 'admin-order-desk')
  return (
    <Loaded state={data.state} reload={data.reload} label="Loading order desk activity…">
      {(d) => {
        const o = d.overview
        return (
          <AdminPage title="Order desk" subtitle="Monitoring only: order approval stays with the order desk. Open any order to see its history (and intervene if needed).">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat icon="clock" label="Pending review" value={o.pending_review} tone={o.pending_review ? 'warn' : 'plain'} />
              <Stat icon="checkCircle" label="Accepted today" value={o.confirmed_today} tone="good" hint={`${o.confirmed_total} in total`} />
              <Stat icon="xCircle" label="Rejected today" value={o.rejected_today} hint={`${o.rejected_total} in total`} />
              <Stat icon="alert" label="Stock or credit issues" value={o.with_stock_or_credit_issues} tone={o.with_stock_or_credit_issues ? 'bad' : 'plain'} hint="Open orders" />
              <Stat icon="edit" label="Orders corrected" value={d.corrected_orders_30d} hint={`Last 30 days · ${d.corrected_orders_total} in total`} />
              <Stat icon="download" label="Exported to Tally" value={d.tally_exported} tone="good" />
              <Stat icon="download" label="Not yet in Tally" value={d.tally_not_exported} tone={d.tally_not_exported ? 'warn' : 'plain'} hint="Confirmed orders" />
            </div>
            <div className="flex flex-wrap gap-3 text-sm font-bold">
              <Link to="/desk/incoming" className="text-leaf-700">Incoming queue →</Link>
              <Link to="/desk/clarification" className="text-leaf-700">Clarification →</Link>
              <Link to="/desk/confirmed" className="text-leaf-700">Confirmed & Tally →</Link>
              <Link to="/desk/rejected" className="text-leaf-700">Rejected →</Link>
            </div>
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
              <Card title="Actions per person (30 days)" padded={false}>
                <DataTable rows={d.people} rowKey={(p) => p.id} empty="No order desk actions yet" columns={[
                  { header: 'Person', cell: (p) => <><span className="font-semibold text-ink">{p.name}</span><span className="block text-xs text-ink-soft">{ROLE_LABELS[p.role]}</span></> },
                  { header: 'Confirmed', align: 'right', cell: (p) => p.actions.CONFIRMED ?? 0 },
                  { header: 'Rejected', align: 'right', cell: (p) => p.actions.REJECTED ?? 0 },
                  { header: 'Clarification', align: 'right', cell: (p) => p.actions.CLARIFICATION_REQUESTED ?? 0 },
                  { header: 'Corrections', align: 'right', cell: (p) => p.actions.CORRECTED ?? 0 },
                  { header: 'Exports', align: 'right', cell: (p) => p.actions.EXPORTED ?? 0 },
                ]} />
              </Card>
              <Card title="Recent order desk actions" actions={<Link to="/admin/audit?source=orders" className="text-sm font-bold text-leaf-700">Audit log →</Link>} padded={false}>
                <ul className="divide-y divide-gray-100">
                  {d.recent.map((e) => (
                    <li key={e.id} className="px-4 py-2.5 text-sm">
                      <Link to={`/desk/orders/${e.entity_id}`} className="font-bold text-ink hover:text-leaf-700">{ACTION_LABELS[e.action] ?? e.action} · {e.label}</Link>
                      <span className="block text-xs text-ink-soft">{e.actor?.name ?? 'user not recorded'} · {dateTime(e.at)}{e.message ? ` · ${e.message}` : ''}{describeChange(e) && !e.message ? ` · ${describeChange(e)}` : ''}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </AdminPage>
        )
      }}
    </Loaded>
  )
}

type AiState = 'all' | 'draft' | 'open' | 'APPROVED' | 'REJECTED'

/** AI order capture: messages, what was extracted, confidence, alternatives, and the result. */
export function AiOrdersPage() {
  const [state, setState] = useState<AiState>('all')
  const [page, setPage] = useState(1)
  const data = useLoad((t, s) => admin.aiOrders(t, { state, page, limit: 10 }, s), `ai|${state}|${page}`)
  return (
    <AdminPage title="AI orders" subtitle="Read-only. Every AI order is confirmed by the customer and then reviewed by the order desk; nothing here bypasses that.">
      <Loaded state={data.state} reload={data.reload}>
        {(d) => {
          const st = d.stats
          return (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                <Stat icon="message" label="Messages read" value={Number(st.extractions)} />
                <Stat icon="orders" label="Became orders" value={Number(st.ordered)} hint={`${Number(st.extractions) - Number(st.ordered)} left as drafts`} />
                <Stat icon="checkCircle" label="Confirmed" value={Number(st.confirmed)} tone="good" />
                <Stat icon="xCircle" label="Rejected" value={Number(st.rejected)} />
                <Stat icon="sparkles" label="Average match" value={st.average_confidence ? `${Math.round(Number(st.average_confidence) * 100)}%` : '—'}
                  hint={`${st.clarification_lines} of ${st.lines} lines needed clarification`} />
              </div>
              <Tabs value={state} onChange={(v) => { setState(v); setPage(1) }} tabs={[['all', 'All'], ['draft', 'Drafts (no order)'], ['open', 'At order desk'], ['APPROVED', 'Confirmed'], ['REJECTED', 'Rejected']]} />
              {d.items.length === 0 ? <Notice>No AI orders here.</Notice> : d.items.map((x) => (
                <Card key={x.id} title={<span>{x.shop_name ?? 'Retailer'} <span className="text-sm font-normal text-ink-soft">· {dateTime(x.created_at)}</span></span>}
                  actions={x.order ? <Link to={`/desk/orders/${x.order.id}`} className="flex items-center gap-2 text-sm font-bold text-leaf-700">{x.order.order_number} <StatusBadge status={x.order.status} /></Link> : <Pill tone="gray">Draft · {x.status.toLowerCase()}</Pill>}>
                  <p className="rounded-lg bg-gray-50 p-3 text-sm text-ink"><span className="mr-2 text-xs font-bold uppercase text-ink-soft">{{ TEXT: 'Text', IMAGE: 'Photo', VOICE: 'Voice' }[x.input_type]}</span>“{x.original_message}”</p>
                  <ul className="mt-3 divide-y divide-gray-100 text-sm">
                    {x.lines.map((l, i) => {
                      const pct = Math.round(Number(l.confidence) * 100)
                      return (
                        <li key={i} className="flex flex-wrap items-start justify-between gap-2 py-2">
                          <span className="min-w-0">
                            <span className="text-ink">“{l.original_text}” → <b>{l.extracted_name}</b>{l.quantity ? ` · ${qty(l.quantity)} ${l.unit ?? ''}` : ''}</span>
                            {l.alternatives.length > 0 && <span className="block text-xs text-ink-soft">Alternatives: {l.alternatives.map((a) => a.name ?? a.sku).filter(Boolean).join(', ')}</span>}
                            {l.evidence.length > 0 && <span className="block text-xs text-ink-soft">Evidence: {l.evidence.join(' · ')}</span>}
                            {l.clarification_reason && <span className="block text-xs text-mango-600">{l.clarification_reason}</span>}
                          </span>
                          <span className="flex shrink-0 gap-1">
                            {l.requires_clarification && <Pill tone="amber">Needed clarification</Pill>}
                            <Pill tone={pct >= d.low_confidence_percent ? 'green' : 'amber'}>{pct}% match</Pill>
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                  {x.order && <p className="mt-2 text-sm text-ink-soft">Result: {STATUS_LABELS[x.order.status]} · {rupees(x.order.grand_total)}</p>}
                </Card>
              ))}
              <Pager page={page} total={d.total} limit={10} onPage={setPage} />
            </>
          )
        }}
      </Loaded>
    </AdminPage>
  )
}

/** Offline sync monitoring (server side): per-salesman sync state, offline orders and failures. */
export function SyncMonitorPage() {
  const data = useLoad((t, s) => admin.sync(t, s), 'admin-sync')
  const [tab, setTab] = useState<'salesmen' | 'orders' | 'failures'>('salesmen')
  return (
    <Loaded state={data.state} reload={data.reload}>
      {(d) => {
        const total = Object.values(d.offline_counts).reduce((a, b) => a + b, 0)
        const conflicts = d.offline_orders.filter((o) => o.hold_reason?.startsWith('Offline order needs review'))
        return (
          <AdminPage title="Offline sync" subtitle="What reached the server from salesmen’s phones. Orders still waiting on a phone are only known from what the phone reports.">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat icon="cloudOff" label="Offline orders synced" value={total} hint={`${d.offline_counts.APPROVED ?? 0} confirmed`} />
              <Stat icon="alert" label="Sync conflicts" value={conflicts.length} tone={conflicts.length ? 'warn' : 'plain'} hint="Held for the order desk (data changed)" />
              <Stat icon="xCircle" label="Failed syncs (7 days)" value={d.failures_7d} tone={d.failures_7d ? 'bad' : 'plain'} hint="Refused by the server" />
              <Stat icon="sync" label="Waiting on phones" value={d.salesmen.reduce((a, s) => a + (s.sync?.pending_orders ?? 0), 0)} hint="As last reported" />
            </div>
            <Tabs value={tab} onChange={setTab} tabs={[['salesmen', 'Salesmen'], ['orders', 'Offline orders'], ['failures', 'Failed syncs']]} />
            {tab === 'salesmen' && (
              <DataTable rows={d.salesmen} rowKey={(s) => s.salesman.id} empty="No salesmen" columns={[
                { header: 'Salesman', cell: (s) => <Link to={`/admin/salesmen/${s.salesman.id}`} className="font-semibold text-ink hover:text-leaf-700">{s.salesman.name}</Link> },
                { header: 'Last sync', cell: (s) => <SyncBadge sync={s.sync} /> },
                { header: 'Waiting', align: 'right', cell: (s) => `${s.sync?.pending_orders ?? 0} orders · ${s.sync?.pending_visits ?? 0} visits` },
                { header: 'Failed', align: 'right', cell: (s) => s.sync?.failed_orders ?? 0 },
                { header: 'Last error', cell: (s) => s.sync?.last_error ?? '—', wide: true },
              ]} />
            )}
            {tab === 'orders' && (
              <DataTable rows={d.offline_orders} rowKey={(o) => o.id} empty="No offline orders yet" columns={[
                { header: 'Order', cell: (o) => <Link to={`/desk/orders/${o.id}`} className="font-semibold text-leaf-700">{o.order_number}</Link> },
                { header: 'Retailer', cell: (o) => o.retailer.shop_name },
                { header: 'Salesman', cell: (o) => o.salesman },
                { header: 'Created on phone', cell: (o) => (o.client_created_at ? dateTime(o.client_created_at) : '—') },
                { header: 'Synced', cell: (o) => dateTime(o.created_at), wide: true },
                { header: 'Status', cell: (o) => <StatusBadge status={o.status} /> },
                { header: 'Why held / rejected', cell: (o) => o.hold_reason?.replace(/^Offline order needs review:\s*/, '') ?? o.rejection_reason ?? '—', wide: true },
              ]} />
            )}
            {tab === 'failures' && (
              <>
                <Notice>These orders stayed on the salesman’s phone as “Sync failed”. The salesman can fix and retry or discard them; the reason is the server’s answer.</Notice>
                <DataTable rows={d.failures} rowKey={(f) => f.id} empty="No failed syncs" columns={[
                  { header: 'When', cell: (f) => dateTime(f.at) },
                  { header: 'Salesman', cell: (f) => f.salesman ?? '—' },
                  { header: 'Device order', cell: (f) => <span className="font-mono text-xs">{f.client_order_id}</span>, wide: true },
                  { header: 'Error', cell: (f) => <Pill tone="red">{f.error_code}</Pill> },
                  { header: 'Why', cell: (f) => f.message },
                  { header: 'Lines', align: 'right', cell: (f) => f.items?.length ?? 0, wide: true },
                ]} />
              </>
            )}
          </AdminPage>
        )
      }}
    </Loaded>
  )
}
