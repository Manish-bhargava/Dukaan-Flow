import { useState } from 'react'
import { listOrders } from '../../api/orders'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, Empty, ErrorBox, Loading, StatusBadge } from '../../components/ui'
import { dateTime, plural, rupees } from '../../format'

export function OrdersPage() {
  const [limit, setLimit] = useState(20)
  const orders = useLoad((t, s) => listOrders(t, { limit }, s), `orders-${limit}`)
  return (
    <>
      <h1 className="text-xl font-extrabold text-ink">My orders</h1>
      <div className="mt-4">
        {orders.state.status === 'error' ? (
          <ErrorBox message={orders.state.message} onRetry={orders.reload} />
        ) : orders.state.status === 'loading' ? (
          <Loading label="Loading orders…" />
        ) : orders.state.data.items.length === 0 ? (
          <Empty title="No orders yet">
            Start from the <Link to="/home" className="font-bold text-leaf-700 underline">catalogue</Link>.
          </Empty>
        ) : (
          <>
            <ul className="divide-y divide-gray-200 border-y border-gray-200">
              {orders.state.data.items.map((o) => (
                <li key={o.id}>
                  <Link to={`/orders/${o.id}`} className="flex items-center justify-between gap-3 py-4 hover:bg-gray-50">
                    <div>
                      <p className="font-bold text-ink">{o.order_number}</p>
                      <p className="text-xs text-ink-soft">
                        {dateTime(o.created_at)} · {plural(o.item_count, 'item')}
                        {o.source === 'AI' ? ' · from message' : ''}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-extrabold text-ink">{rupees(o.grand_total)}</p>
                      <StatusBadge status={o.status} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            {orders.state.data.total > orders.state.data.items.length && (
              <div className="mt-4 text-center">
                <Button variant="secondary" busy={orders.loading} onClick={() => setLimit((n) => n + 20)}>
                  Show more
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}
