import { useState } from 'react'
import { Link } from '../../components/Link'
import { ago } from '../../format'
import { useSalesman } from '../../salesman/SalesmanContext'
import { Card, EmptyState, IconTile, ListGroup, ListRow, Screen, SectionLabel } from '../../salesman/ui'

export function SalesmanHome({ name }: { name: string }) {
  const { bundle, visits, pendingCount, today, lastSyncAt } = useSalesman()
  const openVisit = visits.find((v) => v.ended_at === null)
  const todaysVisits = today.visits
  const [dateLabel] = useState(() => new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }))

  return (
    <Screen title={`Namaste, ${name.split(' ')[0]}`} subtitle={dateLabel}>
      {openVisit && (
        <Link to={`/salesman/visit/${openVisit.retailer_id}`} className="block rounded-2xl bg-mango-300 p-4 shadow-sm active:bg-mango-400">
          <p className="text-[13px] font-semibold uppercase tracking-wide text-leaf-950/70">Visit in progress</p>
          <p className="mt-0.5 text-[19px] font-extrabold text-leaf-950">{openVisit.shop_name}</p>
          <p className="mt-0.5 text-[14px] text-leaf-950/80">Started {ago(openVisit.started_at)} · Tap to continue</p>
        </Link>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat to="#todays-visits" value={today.shopsVisitedToday} label="Shops visited today" />
        <Stat to="/salesman/orders" value={today.ordersToday} label="Orders placed today" />
        <Stat to="/salesman/retailers" value={today.assignedRetailers} label="Assigned retailers" />
        <Stat to="/salesman/sync" value={pendingCount} label="Waiting to sync" tone={pendingCount ? 'mango' : undefined} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <SectionLabel>Quick actions</SectionLabel>
          <ListGroup>
            <ListRow to="/salesman/retailers" leading={<IconTile name="store" />} title="Visit a retailer"
              subtitle={bundle ? `${bundle.retailers.length} assigned retailers` : 'Download your retailers first'} />
            <ListRow to="/salesman/sync" leading={<IconTile name="sync" tone={pendingCount ? 'mango' : 'leaf'} />} title="Offline sync"
              subtitle={`${pendingCount ? `${pendingCount} waiting to sync` : 'All synced'} · ${lastSyncAt ? `last sync ${ago(lastSyncAt)}` : bundle ? `data from ${ago(bundle.synced_at)}` : 'not synced yet'}`} />
            <ListRow to="/salesman/orders" leading={<IconTile name="orders" tone="gray" />} title="My orders" subtitle="Status of orders you placed" />
          </ListGroup>
        </div>
        <div id="todays-visits" className="scroll-mt-32">
          <SectionLabel>Today’s visits{!today.fromServer && <span className="ml-1 normal-case">(this phone only, until online)</span>}</SectionLabel>
          {todaysVisits.length === 0 ? (
            <EmptyState icon="clock" title="No visits yet today">Open a retailer and tap Start visit.</EmptyState>
          ) : (
            <ListGroup>
              {todaysVisits.map((v) => (
                <ListRow key={v.id} to={`/salesman/retailers/${v.retailer_id}`} leading={<IconTile name="store" tone={v.ended_at ? 'gray' : 'mango'} />}
                  title={v.shop_name} subtitle={`${timeOf(v.started_at)}${v.synced ? '' : ' · on this phone, not synced yet'}`}
                  trailing={<span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${
                    !v.ended_at ? 'bg-mango-100 text-mango-600' : v.outcome === 'ORDER_PLACED' ? 'bg-leaf-50 text-leaf-700' : 'bg-gray-100 text-ink-soft'}`}>
                    {!v.ended_at ? 'In progress' : v.outcome === 'ORDER_PLACED' ? 'Order placed' : 'No order'}
                  </span>} />
              ))}
            </ListGroup>
          )}
        </div>
      </div>
    </Screen>
  )
}

const timeOf = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })

function Stat({ to, value, label, tone }: { to: string; value: number; label: string; tone?: 'mango' }) {
  const body = (
    <Card className={`h-full transition hover:ring-leaf-300 active:bg-gray-50 ${tone === 'mango' ? 'bg-mango-100/60' : ''}`}>
      <p className="text-[32px] font-extrabold leading-none text-ink">{value}</p>
      <p className="mt-1.5 text-[14px] font-medium text-ink-soft">{label}</p>
    </Card>
  )
  return to.startsWith('#') ? <a href={to} className="block">{body}</a> : <Link to={to} className="block">{body}</Link>
}
