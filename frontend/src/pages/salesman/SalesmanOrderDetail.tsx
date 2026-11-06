import type { ReactNode } from 'react'
import { getOrder } from '../../api/orders'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { OrderLines } from '../../components/OrderLines'
import { ErrorBox, Loading, StatusBadge } from '../../components/ui'
import { dateTime, plural, rupees, SYNC_LABELS, SYNC_STYLES } from '../../format'
import { useSalesman } from '../../salesman/SalesmanContext'
import { Card, EmptyState, Icon, ListGroup, ListRow, Screen, SectionLabel } from '../../salesman/ui'
import { TotalsTable } from '../retailer/CartPage'

const BACK = { to: '/salesman/orders', label: 'Orders' }

/** An order the backend has received (the same order the retailer and order desk see). */
export function SalesmanServerOrder({ orderId }: { orderId: string }) {
  const { online } = useSalesman()
  const order = useLoad((t, s) => getOrder(t, orderId, s), orderId)
  if (order.state.status !== 'ready') {
    return (
      <Screen title="Order" back={BACK}>
        {!online ? <EmptyState icon="cloudOff" title="You are offline">Order details need internet.</EmptyState>
          : order.state.status === 'error' ? <ErrorBox message={order.state.message} onRetry={order.reload} /> : <Loading label="Loading order…" />}
      </Screen>
    )
  }
  const o = order.state.data
  return (
    <Screen title={o.retailer.shop_name} subtitle={o.order_number} back={BACK} action={<StatusBadge status={o.status} />}>
      <Card className="space-y-1 text-[14px] text-ink-soft">
        <p>Placed {dateTime(o.client_created_at ?? o.created_at)} by {o.created_by.name}</p>
        <p>{o.created_offline ? 'Created offline, synced later' : 'Created online'}</p>
      </Card>
      {o.hold_reason && <Note tone="warn">On hold: {o.hold_reason}</Note>}
      {o.status === 'CREDIT_HOLD' && <Note tone="warn">Above the shop’s available credit: waiting for the order desk.</Note>}
      {o.status === 'CLARIFICATION_REQUIRED' && <Note tone="warn">Order desk needs a clarification: {o.clarification_message}</Note>}
      {o.rejection_reason && <Note tone="warn">Rejected: {o.rejection_reason}</Note>}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-2xl bg-white px-4 ring-1 ring-black/5"><OrderLines order={o} /></div>
        <Card className="lg:sticky lg:top-36"><TotalsTable totals={o} /></Card>
      </div>
    </Screen>
  )
}

/** An order on this phone; updates live while it syncs. */
export function SalesmanLocalOrder({ clientOrderId }: { clientOrderId: string }) {
  const { orders, retryOrder } = useSalesman()
  const o = orders.find((x) => x.client_order_id === clientOrderId)
  if (!o) return <Screen title="Order" back={BACK}><EmptyState icon="orders" title="Order not found on this phone" /></Screen>
  const estimate = o.items.reduce((s, i) => s + i.quantity * Number(i.case_price), 0)
  const message = {
    saved_offline: 'Saved on this phone. It will be sent automatically when there is internet. It is not with the distributor yet.',
    pending_sync: 'Waiting to be sent to the distributor.',
    syncing: 'Sending to the distributor…',
    synced: 'Received by the distributor.',
    sync_failed: `Could not be sent: ${o.last_error}`,
  }[o.status]

  return (
    <Screen title={o.shop_name} subtitle={`Ref ${o.client_order_id.slice(0, 8)} · ${dateTime(o.created_at)}`} back={{ to: '/salesman/sync', label: 'Sync' }}
      action={<span className={`rounded-full px-2.5 py-1 text-[13px] font-semibold ${SYNC_STYLES[o.status]}`}>{SYNC_LABELS[o.status]}</span>}>
      <Note tone={o.status === 'synced' ? 'success' : o.status === 'sync_failed' ? 'warn' : 'info'}>{message}</Note>
      {o.server && (o.server.status === 'ON_HOLD' || o.server.status === 'CREDIT_HOLD') && (
        <Note tone="warn">
          Needs review by the order desk: {o.server.hold_reason?.replace(/^Offline order needs review:\s*/, '') ?? 'above the shop’s available credit'}. Your order below is kept exactly as you entered it.
        </Note>
      )}
      {o.server && (
        <Link to={`/salesman/orders/${o.server.id}`} className="flex items-center justify-between rounded-2xl bg-white p-4 ring-1 ring-black/5 active:bg-gray-50">
          <span>
            <span className="block text-[16px] font-semibold text-ink">{o.server.order_number}</span>
            <span className="text-[13px] text-ink-soft">{rupees(o.server.grand_total)} · view full order</span>
          </span>
          <span className="flex items-center gap-2"><StatusBadge status={o.server.status} /><Icon name="chevronRight" className="h-4 w-4 text-gray-300" /></span>
        </Link>
      )}
      {o.status === 'sync_failed' && (
        <button type="button" onClick={() => void retryOrder(o.client_order_id)} className="min-h-12 w-full rounded-2xl bg-leaf-700 text-[16px] font-semibold text-white">Retry</button>
      )}
      <div>
        <SectionLabel>{plural(o.items.length, 'product')}</SectionLabel>
        <ListGroup>
          {o.items.map((i) => (
            <ListRow key={i.product_id} title={i.name}
              subtitle={`${i.sku} · ${rupees(i.case_price)} / ${i.order_unit} at the time${i.schemes?.length ? ` · ${i.schemes.map((sch) => sch.description).join(', ')}` : ''}`}
              trailing={<><p className="text-[15px] font-semibold text-ink">{plural(i.quantity, i.order_unit)}</p><p className="text-[12px] text-ink-soft">≈ {rupees(i.quantity * Number(i.case_price))}</p></>} />
          ))}
        </ListGroup>
      </div>
      {!o.server && <p className="px-1 text-[14px] text-ink-soft">Estimate ≈ <b className="text-ink">{rupees(estimate)}</b> before schemes and GST; the final amount is calculated when synced.</p>}
      {o.remarks && <p className="px-1 text-[14px] text-ink-soft">Note: {o.remarks}</p>}
    </Screen>
  )
}

function Note({ tone, children }: { tone: 'info' | 'warn' | 'success'; children: ReactNode }) {
  const s = { info: 'bg-white text-ink ring-black/5', warn: 'bg-orange-50 text-orange-900 ring-orange-200', success: 'bg-leaf-50 text-leaf-800 ring-leaf-200' }[tone]
  return <div className={`rounded-2xl p-4 text-[14px] ring-1 ${s}`}>{children}</div>
}
