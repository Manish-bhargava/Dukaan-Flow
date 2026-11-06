import { useState } from 'react'
import { ago, dateTime, rupees, SYNC_LABELS, SYNC_STYLES } from '../../format'
import { useSalesman, type ActionResult, type LocalOrder } from '../../salesman/SalesmanContext'
import { Card, EmptyState, Icon, ListGroup, ListRow, PrimaryButton, Screen, Segmented } from '../../salesman/ui'

type Group = 'waiting' | 'syncing' | 'failed' | 'synced'
const GROUP_OF: Record<LocalOrder['status'], Group> = {
  saved_offline: 'waiting', pending_sync: 'waiting', syncing: 'syncing', sync_failed: 'failed', synced: 'synced',
}

/** Offline orders on this phone, grouped by sync status, plus the downloaded data. */
export function SyncPage() {
  const { online, syncing, downloading, bundle, bundleError, orders, visits, syncNow, refreshBundle, retryOrder, discardOrder, lastSyncAt } = useSalesman()
  const [running, setRunning] = useState<'sync' | 'download' | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)

  /** Run a sync/download with visible progress (at least ~0.6 s) and then show what happened. */
  async function run(kind: 'sync' | 'download', action: () => Promise<ActionResult>) {
    setRunning(kind)
    setResult(null)
    const started = Date.now()
    const outcome = await action()
    const rest = 600 - (Date.now() - started)
    if (rest > 0) await new Promise((resolve) => window.setTimeout(resolve, rest))
    setRunning(null)
    setResult(outcome)
  }
  const busySync = running === 'sync' || syncing
  const busyDownload = running === 'download' || downloading
  const counts = { waiting: 0, syncing: 0, failed: 0, synced: 0 }
  for (const o of orders) counts[GROUP_OF[o.status]]++
  const hasWaitingVisits = visits.some((v) => !v.synced)
  // Until the salesman picks a tab, show what needs attention first.
  const [chosen, setGroup] = useState<Group | null>(null)
  const group: Group = chosen ?? (counts.failed ? 'failed' : counts.waiting || counts.syncing || hasWaitingVisits ? 'waiting' : 'synced')
  const [openedAt] = useState(() => Date.now())
  const unsentOrders = new Set(orders.filter((o) => o.status !== 'synced').map((o) => o.client_order_id))
  const visitsWaiting = visits.filter((v) => !v.synced && !(v.client_order_id && unsentOrders.has(v.client_order_id)))
  const shown = orders.filter((o) => GROUP_OF[o.status] === group)

  return (
    <Screen title="Offline sync" subtitle="Orders are saved on this phone first and sent when there is internet.">
      <div className="grid items-start gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Card className="space-y-3 lg:sticky lg:top-36">
        <div className="flex items-center gap-3">
          <span className={`flex h-11 w-11 items-center justify-center rounded-full ${online ? 'bg-leaf-50 text-leaf-700' : 'bg-gray-800 text-white'}`}>
            <Icon name={online ? 'check' : 'cloudOff'} />
          </span>
          <div>
            <p className="text-[17px] font-semibold text-ink">{online ? (busySync ? 'Syncing…' : busyDownload ? 'Downloading…' : 'Online') : 'Offline'}</p>
            <p className="text-[13px] text-ink-soft">{lastSyncAt ? `Last successful sync ${ago(lastSyncAt)}` : 'Not synced yet'}</p>
            <p className="text-[13px] text-ink-soft">{bundle ? `Retailers, products and prices from ${ago(bundle.synced_at)}` : 'No data downloaded yet'}</p>
          </div>
        </div>
        {bundleError && !result && <p className="text-[13px] text-red-700">{bundleError}</p>}
        {bundle && openedAt - new Date(bundle.synced_at).getTime() > 12 * 3600_000 && (
          <p className="text-[13px] text-orange-700">Prices, stock or credit may have changed since then. Download the latest data when online.</p>
        )}
        <div className="grid grid-cols-2 gap-2">
          <PrimaryButton disabled={busySync || busyDownload} onClick={() => void run('sync', syncNow)} className="min-h-11 text-[15px]">
            <Icon name="sync" className={`h-[18px] w-[18px] ${busySync ? 'animate-spin' : ''}`} /> {busySync ? 'Syncing…' : 'Sync now'}
          </PrimaryButton>
          <PrimaryButton tone="mango" disabled={busySync || busyDownload} onClick={() => void run('download', refreshBundle)} className="min-h-11 text-[15px]">
            <Icon name={busyDownload ? 'sync' : 'download'} className={`h-[18px] w-[18px] ${busyDownload ? 'animate-spin' : ''}`} /> {busyDownload ? 'Downloading…' : 'Get data'}
          </PrimaryButton>
        </div>
        {result && (
          <p role="status" className={`rounded-xl px-3 py-2 text-[14px] ${result.ok ? 'bg-leaf-50 text-leaf-800' : 'bg-orange-50 text-orange-900'}`}>
            {result.message}
          </p>
        )}
      </Card>

      <div className="space-y-4">
      <Segmented value={group} onChange={setGroup} options={[
        { value: 'waiting', label: `Waiting ${counts.waiting + visitsWaiting.length || ''}`.trim() },
        { value: 'syncing', label: `Syncing ${counts.syncing || ''}`.trim() },
        { value: 'failed', label: `Failed ${counts.failed || ''}`.trim() },
        { value: 'synced', label: 'Synced' },
      ]} />

      {visitsWaiting.length > 0 && (group === 'waiting' || group === 'syncing') && (
        <ListGroup>
          {visitsWaiting.map((v) => (
            <ListRow key={v.id} to={`/salesman/retailers/${v.retailer_id}`} title={`Visit record · ${v.shop_name}`}
              subtitle={`${dateTime(v.started_at)} · ${!v.ended_at ? 'visit in progress' : v.outcome === 'ORDER_PLACED' ? 'order placed' : 'no order'}`}
              trailing={<span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${SYNC_STYLES.pending_sync}`}>{SYNC_LABELS.pending_sync}</span>} />
          ))}
        </ListGroup>
      )}

      {shown.length === 0 && (visitsWaiting.length === 0 || group === 'failed' || group === 'synced') ? (
        <EmptyState icon={group === 'failed' ? 'check' : 'sync'} title={
          { waiting: 'Nothing waiting', syncing: 'Nothing syncing right now', failed: 'No failed orders', synced: 'No synced orders on this phone yet' }[group]
        } />
      ) : shown.length === 0 ? null : (
        <ListGroup>
          {shown.map((o) => (
            <SyncRow key={o.client_order_id} order={o} onRetry={() => void retryOrder(o.client_order_id)} onDiscard={() => {
              if (window.confirm(`Discard this order for ${o.shop_name}? It has not reached the distributor.`)) void discardOrder(o.client_order_id)
            }} />
          ))}
        </ListGroup>
      )}
      </div>
      </div>
    </Screen>
  )
}

function SyncRow({ order: o, onRetry, onDiscard }: { order: LocalOrder; onRetry: () => void; onDiscard: () => void }) {
  const estimate = o.items.reduce((s, i) => s + i.quantity * Number(i.case_price), 0)
  const to = o.server ? `/salesman/orders/${o.server.id}` : `/salesman/orders/local/${o.client_order_id}`
  return (
    <>
      <ListRow
        to={to}
        title={o.shop_name}
        subtitle={<>{o.server ? o.server.order_number : `Ref ${o.client_order_id.slice(0, 8)}`} · {dateTime(o.created_at)}{o.last_error && o.status !== 'synced' ? <><br /><span className="text-red-700">{o.last_error}</span></> : null}</>}
        trailing={<>
          <p className="text-[15px] font-semibold text-ink">{o.server ? rupees(o.server.grand_total) : `≈ ${rupees(estimate)}`}</p>
          <span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${SYNC_STYLES[o.status]}`}>{SYNC_LABELS[o.status]}</span>
        </>}
      />
      {o.status === 'sync_failed' && (
        <li className="grid grid-cols-2 gap-2 px-4 pb-3">
          <button type="button" onClick={onRetry} className="min-h-11 rounded-xl bg-leaf-700 text-[15px] font-semibold text-white active:bg-leaf-800">Retry</button>
          <button type="button" onClick={onDiscard} className="min-h-11 rounded-xl bg-white text-[15px] font-semibold text-red-700 ring-1 ring-red-200 active:bg-red-50">Discard</button>
        </li>
      )}
    </>
  )
}
