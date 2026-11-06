import { Fragment, useEffect, useState } from 'react'
import { listOrders, type OrderStatus, type OrderSummary } from '../../api/orders'
import { useToken } from '../../auth/useApi'
import { StatusBadge } from '../../components/ui'
import { dateTime, rupees, SYNC_LABELS, SYNC_STYLES } from '../../format'
import { idbGet, idbPut } from '../../salesman/idb'
import { useSalesman } from '../../salesman/SalesmanContext'
import { EmptyState, IconTile, ListGroup, ListRow, Screen, SectionLabel, Segmented } from '../../salesman/ui'

type Filter = 'all' | 'unsynced' | 'confirmed' | 'review' | 'rejected'
const MATCH: Record<Exclude<Filter, 'unsynced'>, (s: OrderStatus) => boolean> = {
  all: () => true,
  confirmed: (s) => s === 'APPROVED',
  review: (s) => s === 'PENDING' || s === 'ON_HOLD' || s === 'CREDIT_HOLD' || s === 'CLARIFICATION_REQUIRED',
  rejected: (s) => s === 'REJECTED',
}

/** All orders this salesman placed: those still on the phone (with their sync status) and
 *  those the distributor has received (from the API, cached for offline viewing). */
export function SalesmanOrdersPage({ userId }: { userId: string }) {
  const { orders, online, retryOrder, syncing } = useSalesman()
  const token = useToken()
  const [history, setHistory] = useState<OrderSummary[] | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const historyKey = `history:${userId}`
  const syncedCount = orders.filter((o) => o.status === 'synced').length
  const unsent = orders.filter((o) => o.status !== 'synced')

  useEffect(() => {
    void idbGet<OrderSummary[]>('kv', historyKey).then((cached) => cached && setHistory(cached))
    if (!online || !token) return
    const controller = new AbortController()
    listOrders(token, { created_by_me: true, limit: 50 }, controller.signal)
      .then((res) => {
        setHistory(res.data.items)
        void idbPut('kv', res.data.items, historyKey)
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [online, token, historyKey, syncedCount])

  const showLocal = filter === 'all' || filter === 'unsynced'
  const shown = filter === 'unsynced' ? [] : (history ?? []).filter((o) => MATCH[filter](o.status))
  return (
    <Screen title="My orders" subtitle="Every order you placed, with its sync and order status">
      <div className="max-w-2xl overflow-x-auto"><Segmented value={filter} onChange={setFilter} options={[
        { value: 'all', label: 'All' }, { value: 'unsynced', label: `Unsynced${unsent.length ? ` ${unsent.length}` : ''}` },
        { value: 'confirmed', label: 'Confirmed' }, { value: 'review', label: 'In review' }, { value: 'rejected', label: 'Rejected' },
      ]} /></div>

      {showLocal && unsent.length > 0 && (
        <div>
          <SectionLabel>On this phone, not sent yet</SectionLabel>
          <ListGroup>
            {unsent.map((o) => (
              <Fragment key={o.client_order_id}>
                <ListRow
                  to={`/salesman/orders/local/${o.client_order_id}`}
                  leading={<IconTile name="cloudOff" tone={o.status === 'sync_failed' ? 'red' : 'mango'} />}
                  title={o.shop_name}
                  subtitle={<>{`Ref ${o.client_order_id.slice(0, 8)}`} · {dateTime(o.created_at)} · {o.created_offline ? 'created offline' : 'created online'}
                    {o.last_error && o.status === 'sync_failed' ? <><br /><span className="text-red-700">{o.last_error}</span></> : null}</>}
                  trailing={<>
                    <p className="text-[15px] font-semibold text-ink">≈ {rupees(o.items.reduce((sum, i) => sum + i.quantity * Number(i.case_price), 0))}</p>
                    <span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${SYNC_STYLES[o.status]}`}>{SYNC_LABELS[o.status]}</span>
                  </>}
                />
                {o.status === 'sync_failed' && (
                  <li className="px-4 pb-3">
                    <button type="button" disabled={syncing} onClick={() => void retryOrder(o.client_order_id)}
                      className="min-h-11 w-full rounded-xl bg-leaf-700 text-[15px] font-semibold text-white active:bg-leaf-800 disabled:opacity-50">Retry sync</button>
                  </li>
                )}
              </Fragment>
            ))}
          </ListGroup>
        </div>
      )}

      {filter !== 'unsynced' && (
        <div>
          <SectionLabel>Received by the distributor</SectionLabel>
          {!history ? (
            <EmptyState icon={online ? 'orders' : 'cloudOff'} title={online ? 'Loading…' : 'Connect to load your orders'} />
          ) : shown.length === 0 ? (
            <EmptyState icon="orders" title="No orders here" />
          ) : (
            <ListGroup>
              {shown.map((o) => (
                <ListRow
                  key={o.id}
                  to={`/salesman/orders/${o.id}`}
                  leading={<IconTile name={o.created_offline ? 'cloudOff' : 'orders'} tone={o.created_offline ? 'gray' : 'leaf'} />}
                  title={o.retailer.shop_name}
                  subtitle={<>{o.order_number}<br />{dateTime(o.created_at)} · {o.created_offline ? 'created offline' : 'created online'}</>}
                  trailing={<>
                    <p className="text-[15px] font-semibold text-ink">{rupees(o.grand_total)}</p>
                    <span className="flex justify-end gap-1">
                      <span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${SYNC_STYLES.synced}`}>Synced</span>
                      <StatusBadge status={o.status} />
                    </span>
                  </>}
                />
              ))}
            </ListGroup>
          )}
        </div>
      )}
      {filter === 'unsynced' && unsent.length === 0 && <EmptyState icon="check" title="Everything is synced" />}
    </Screen>
  )
}
