import { t } from '../../i18n'
import { getOrder, type Order } from '../../api/orders'
import { useLoad } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { orderCartLines } from '../../cart/lines'
import { Link } from '../../components/Link'
import { OrderLines } from '../../components/OrderLines'
import { Button, ErrorBox, Loading, Notice, StatusBadge } from '../../components/ui'
import { dateTime } from '../../format'
import { navigate } from '../../router'
import { TotalsTable } from './CartPage'

function statusText(order: Order): string {
  switch (order.status) {
    case 'PENDING':
      return t('Under review: the order desk has received this order but has not accepted it yet.')
    case 'CREDIT_HOLD':
      return t('This order is above your available credit. The order desk will review it.')
    case 'ON_HOLD':
      return t('On hold: {reason}', { reason: order.hold_reason ?? t('the order desk will contact you.') })
    case 'CLARIFICATION_REQUIRED':
      return t('The order desk needs a clarification: {question} Please reply to your salesman or the order desk. Your order is kept as you placed it.', { question: order.clarification_message ?? '' })
    case 'APPROVED':
      return t('Confirmed{date}.', { date: order.approved_at ? t(' on {date}', { date: dateTime(order.approved_at) }) : '' })
    case 'REJECTED':
      return t('Rejected: {reason}', { reason: order.rejection_reason ?? '' })
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
    addLines(orderCartLines(o))
    navigate('/cart')
  }

  return (
    <>
      <Link to="/orders" className="text-sm font-bold text-leaf-700">{t('← My orders')}</Link>
      {justPlaced && (
        <div className="mt-3">
          <Notice tone="success">
            {o.status === 'APPROVED'
              ? t('Order placed and confirmed. Its amount has been added to your outstanding credit.')
              : t('Order sent to the order desk for review. Its amount is held from your credit until they accept or reject it.')}
          </Notice>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-ink">{o.order_number}</h1>
          <p className="text-sm text-ink-soft">
            {t('Placed {date}', { date: dateTime(o.created_at) })}
            {o.source === 'AI' ? t(' · from your message') : ''}
          </p>
        </div>
        <StatusBadge status={o.status} />
      </div>
      <p className="mt-2 text-sm text-ink">{statusText(o)}</p>
      {o.remarks && <p className="mt-1 text-sm text-ink-soft">{t('Your note: {note}', { note: o.remarks })}</p>}

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <OrderLines order={o} />
        <aside className="h-fit rounded-xl border border-gray-200 p-4">
          <h2 className="font-extrabold text-ink">{t('Total')}</h2>
          <TotalsTable totals={o} />
          <Button variant="secondary" className="mt-4 w-full" onClick={repeat}>
            {t('Repeat this order')}
          </Button>
          <p className="mt-2 text-xs text-ink-soft">{t('Adds these items to your cart at today’s prices and schemes.')}</p>
        </aside>
      </div>
    </>
  )
}
