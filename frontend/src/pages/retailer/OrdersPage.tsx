import { t } from '../../i18n'
import { useState } from 'react'
import { listDrafts } from '../../api/aiOrders'
import { listOrders } from '../../api/orders'
import { useLoad } from '../../auth/useApi'
import { useRepeatOrder } from '../../cart/useRepeatOrder'
import { Link } from '../../components/Link'
import { Button, Empty, ErrorBox, Loading, StatusBadge } from '../../components/ui'
import { dateTime, plural, RETAILER_SOURCE_LABELS, rupees } from '../../format'

export function OrdersPage() {
  return (
    <>
      <h1 className="text-xl font-extrabold text-ink">{t('My orders')}</h1>
      <p className="mt-1 text-sm text-ink-soft">
        {t('Under review: received by the order desk, not accepted yet. Confirmed: accepted by the order desk. Tap Repeat to order the same products again.')}
      </p>
      <div className="mt-4 space-y-6">
        <AiDrafts />
        <OrderList />
      </div>
    </>
  )
}

/** The retailer's orders, newest first, with status and source. */
export function OrderList() {
  const [limit, setLimit] = useState(20)
  const orders = useLoad((t, s) => listOrders(t, { limit }, s), `orders-${limit}`)
  const { repeat, busyId, error } = useRepeatOrder()
  if (orders.state.status === 'error') return <ErrorBox message={orders.state.message} onRetry={orders.reload} />
  if (orders.state.status === 'loading') return <Loading label={t('Loading orders…')} />
  const { items, total } = orders.state.data
  if (items.length === 0) {
    return (
      <Empty title={t('No orders yet')}>
        Start from the <Link to="/home" className="font-bold text-leaf-700 underline">catalogue</Link>.
      </Empty>
    )
  }
  return (
    <>
      <ul className="divide-y divide-gray-200 border-y border-gray-200">
        {items.map((o) => (
          <li key={o.id} className="py-3">
            <div className="flex items-center gap-3">
              <Link to={`/orders/${o.id}`} className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-lg py-1 hover:bg-gray-50">
                <div className="min-w-0">
                  <p className="font-bold text-ink">{o.order_number}</p>
                  <p className="text-xs text-ink-soft">
                    {dateTime(o.created_at)} · {plural(o.item_count, 'product')} · {RETAILER_SOURCE_LABELS[o.source]}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-extrabold text-ink">{rupees(o.grand_total)}</p>
                  <StatusBadge status={o.status} />
                </div>
              </Link>
              <Button variant="secondary" busy={busyId === o.id} disabled={busyId !== null} onClick={() => void repeat(o.id)} className="shrink-0">
                {t('Repeat')}
              </Button>
            </div>
            {error?.orderId === o.id && <p className="mt-1 text-sm text-red-700">{error.message}</p>}
          </li>
        ))}
      </ul>
      {total > items.length && (
        <div className="mt-4 text-center">
          <Button variant="secondary" busy={orders.loading} onClick={() => setLimit((n) => n + 20)}>
            {t('Show more')}
          </Button>
        </div>
      )}
    </>
  )
}

/** AI drafts not placed yet: they are not orders, so they are listed separately. */
export function AiDrafts() {
  const drafts = useLoad((t, s) => listDrafts(t, s), 'ai-drafts')
  if (drafts.state.status !== 'ready' || drafts.state.data.length === 0) return null
  return (
    <section aria-labelledby="drafts-title">
      <h2 id="drafts-title" className="text-sm font-extrabold uppercase tracking-wide text-ink-soft">
        {t('Drafts from your messages (not sent yet)')}
      </h2>
      <ul className="mt-2 divide-y divide-gray-200 border-y border-gray-200">
        {drafts.state.data.map((d) => (
          <li key={d.extraction_id}>
            <Link to={`/ai-order?draft=${d.extraction_id}`} className="flex items-center justify-between gap-3 py-3 hover:bg-gray-50">
              <div className="min-w-0">
                <p className="truncate text-sm text-ink">“{d.original_message}”</p>
                <p className="text-xs text-ink-soft">
                  {dateTime(d.created_at)} · {plural(d.item_count, 'line')} · {t('Tap to review and send')}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${d.needs_clarification ? 'bg-mango-100 text-mango-600' : 'bg-gray-100 text-ink-soft'}`}>
                {d.needs_clarification ? t('Needs clarification') : t('Draft')}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
