import { getOrder, type Order } from '../../api/orders'
import { useLoad } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { Link } from '../../components/Link'
import { OrderLines } from '../../components/OrderLines'
import { Button, ErrorBox, Loading, Notice, StatusBadge } from '../../components/ui'
import { dateTime } from '../../format'
import { navigate } from '../../router'
import { TotalsTable } from './CartPage'

function statusText(order: Order): string {
  switch (order.status) {
    case 'PENDING':
      return 'Waiting for the order desk to confirm.'
    case 'CREDIT_HOLD':
      return 'This order is above your available credit. The order desk will review it.'
    case 'ON_HOLD':
      return `On hold: ${order.hold_reason ?? 'the order desk will contact you.'}`
    case 'APPROVED':
      return `Confirmed${order.approved_at ? ` on ${dateTime(order.approved_at)}` : ''}.`
    case 'REJECTED':
      return `Rejected: ${order.rejection_reason ?? ''}`
  }
}

export function OrderDetailPage({ orderId }: { orderId: string }) {
  const order = useLoad((t, s) => getOrder(t, orderId, s), orderId)
  const { addLines } = useCart()
  const justPlaced = new URLSearchParams(window.location.search).has('placed')

  if (order.state.status === 'error') return <ErrorBox message={order.state.message} onRetry={order.reload} />
  if (order.state.status === 'loading') return <Loading label="Loading order…" />
  const o = order.state.data

  function repeat() {
    addLines(o.items.map((i) => ({
      product_id: i.product_id, sku: i.sku, name: i.product_name, pack_size: i.pack_size,
      order_unit: i.order_unit, category: '', quantity: Number(i.paid_quantity),
    })))
    navigate('/cart')
  }

  return (
    <>
      <Link to="/orders" className="text-sm font-bold text-leaf-700">← My orders</Link>
      {justPlaced && (
        <div className="mt-3">
          <Notice tone="success">Order placed. You will see it here when the order desk confirms it.</Notice>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-ink">{o.order_number}</h1>
          <p className="text-sm text-ink-soft">
            Placed {dateTime(o.created_at)}
            {o.source === 'AI' ? ' · from your message' : ''}
          </p>
        </div>
        <StatusBadge status={o.status} />
      </div>
      <p className="mt-2 text-sm text-ink">{statusText(o)}</p>
      {o.remarks && <p className="mt-1 text-sm text-ink-soft">Your note: {o.remarks}</p>}

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <OrderLines order={o} />
        <aside className="h-fit rounded-xl border border-gray-200 p-4">
          <h2 className="font-extrabold text-ink">Total</h2>
          <TotalsTable totals={o} />
          <Button variant="secondary" className="mt-4 w-full" onClick={repeat}>
            Repeat this order
          </Button>
          <p className="mt-2 text-xs text-ink-soft">Adds these items to your cart at today’s prices and schemes.</p>
        </aside>
      </div>
    </>
  )
}
