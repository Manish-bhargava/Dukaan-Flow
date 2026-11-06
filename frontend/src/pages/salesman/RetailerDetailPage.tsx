import { useState } from 'react'
import { StatusBadge } from '../../components/ui'
import { ago, CREDIT_LEVEL_STYLES, creditLevel, dateTime, plural, rupees } from '../../format'
import { navigate } from '../../router'
import { useSalesman } from '../../salesman/SalesmanContext'
import { Avatar, Card, EmptyState, Icon, IconTile, ListGroup, ListRow, PrimaryButton, Screen, SectionLabel } from '../../salesman/ui'

/** One assigned retailer: details, credit and previous orders; Start visit lives here. */
export function RetailerDetailPage({ retailerId }: { retailerId: string }) {
  const { bundle, visits, orders, startVisit } = useSalesman()
  const [busy, setBusy] = useState(false)
  const r = bundle?.retailers.find((x) => x.id === retailerId)
  if (!bundle || !r) {
    return (
      <Screen title="Retailer" back={{ to: '/salesman/retailers', label: 'Retailers' }}>
        <EmptyState icon="store" title="Retailer not found">This shop is not assigned to you, or your data needs refreshing.</EmptyState>
      </Screen>
    )
  }
  const openVisit = visits.find((v) => v.retailer_id === r.id && v.ended_at === null)
  const unsent = orders.filter((o) => o.retailer_id === r.id && o.status !== 'synced')
  const c = r.credit
  const level = c ? creditLevel(c.available_credit, c.credit_limit) : 'low'

  async function start() {
    setBusy(true)
    if (!openVisit) await startVisit(r!.id, r!.shop_name)
    navigate(`/salesman/visit/${r!.id}`)
  }

  return (
    <Screen title={r.shop_name} back={{ to: '/salesman/retailers', label: 'Retailers' }}>
      <div className="grid items-start gap-5 lg:grid-cols-2">
      <div className="space-y-5">
      <Card className="flex items-center gap-4">
        <Avatar name={r.shop_name} size="h-14 w-14 text-lg" />
        <div className="min-w-0 flex-1">
          <p className="text-[17px] font-semibold text-ink">{r.owner_name}</p>
          <p className="text-[14px] text-ink-soft">{r.city}</p>
        </div>
        <a href={`tel:+91${r.phone}`} aria-label={`Call ${r.owner_name}`}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-leaf-700 text-white active:bg-leaf-800">
          <Icon name="phone" />
        </a>
      </Card>

      {r.ordering_restricted_reason && (
        <div role="alert" className="rounded-2xl bg-red-50 p-4 text-[14px] font-semibold text-red-800 ring-1 ring-red-200">
          Ordering is paused for this shop: {r.ordering_restricted_reason}. Orders for it will not be accepted.
        </div>
      )}

      {c && (
        <div className={`rounded-2xl p-4 ring-1 ${CREDIT_LEVEL_STYLES[level].pill}`}>
          <p className="text-[13px] font-semibold">Available credit</p>
          <p className="text-[28px] font-extrabold leading-tight">{rupees(Math.max(0, Number(c.available_credit)))}</p>
          <p className="text-[13px]">of {rupees(c.credit_limit)} · as of {ago(bundle.synced_at)}</p>
        </div>
      )}

      <PrimaryButton tone={openVisit ? 'mango' : 'leaf'} busy={busy} onClick={() => void start()}>
        <Icon name="cart" /> {openVisit ? 'Continue visit' : 'Start visit'}
      </PrimaryButton>
      </div>
      <div className="space-y-5">

      <div>
        <SectionLabel>Shop details</SectionLabel>
        <ListGroup>
          <ListRow href={`tel:+91${r.phone}`} leading={<IconTile name="phone" tone="gray" />} title={`+91 ${r.phone}`} subtitle="Shop contact number" />
          {r.registered_mobiles.map((m) => (
            <ListRow key={m} href={`tel:+91${m}`} leading={<IconTile name="user" tone="gray" />} title={`+91 ${m}`} subtitle="Registered login mobile" />
          ))}
          <ListRow href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${r.shop_name}, ${r.address}, ${r.city}`)}`}
            leading={<IconTile name="pin" tone="gray" />} title={r.address} subtitle={`${r.city} · open in maps`} />
          <ListRow leading={<IconTile name="store" tone="gray" />} title={<span className="font-mono text-[13px]">{r.id}</span>} subtitle={r.gstin ? `Retailer ID · GSTIN ${r.gstin}` : 'Retailer ID'} />
        </ListGroup>
      </div>

      <div>
        <SectionLabel>Previous orders</SectionLabel>
        {unsent.length + r.recent_orders.length === 0 ? (
          <EmptyState icon="orders" title="No orders yet" />
        ) : (
          <ListGroup>
            {unsent.map((o) => (
              <ListRow key={o.client_order_id} to={`/salesman/orders/local/${o.client_order_id}`} title={dateTime(o.created_at)}
                subtitle={plural(o.items.length, 'product')}
                trailing={<span className="rounded-full bg-orange-50 px-2 py-0.5 text-[12px] font-semibold text-orange-700">Not sent yet</span>} />
            ))}
            {r.recent_orders.map((o) => (
              <ListRow key={o.id} to={`/salesman/orders/${o.id}`} title={o.order_number}
                subtitle={`${dateTime(o.created_at)} · ${plural(o.item_count, 'product')}`}
                trailing={<><p className="text-[15px] font-semibold text-ink">{rupees(o.grand_total)}</p><StatusBadge status={o.status} /></>} />
            ))}
          </ListGroup>
        )}
      </div>
      </div>
      </div>
    </Screen>
  )
}
