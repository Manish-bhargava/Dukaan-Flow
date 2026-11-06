import { useState } from 'react'
import { ago } from '../../format'
import { useSalesman } from '../../salesman/SalesmanContext'
import { Link } from '../../components/Link'
import { Avatar, EmptyState, Icon, Screen, SearchField } from '../../salesman/ui'

export function RetailerListPage() {
  const { bundle, visits } = useSalesman()
  const [search, setSearch] = useState('')
  if (!bundle) {
    return (
      <Screen title="Retailers">
        <EmptyState icon="cloudOff" title="No retailers on this phone yet">Connect to the internet once to download your retailers.</EmptyState>
      </Screen>
    )
  }
  const q = search.trim().toLowerCase()
  const digits = q.replace(/\D/g, '')
  const list = bundle.retailers.filter(
    (r) => !q || r.shop_name.toLowerCase().includes(q) || r.owner_name.toLowerCase().includes(q)
      || (digits.length > 0 && [r.phone, ...r.registered_mobiles].some((m) => m.includes(digits))),
  )

  return (
    <Screen title="Retailers" subtitle={`${bundle.retailers.length} assigned to you`}>
      <div className="max-w-xl"><SearchField value={search} onChange={setSearch} placeholder="Search shop name or mobile" /></div>
      {list.length === 0 ? (
        <EmptyState icon="search" title="No retailer matches">Try another name or number.</EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.map((r) => {
            const open = visits.some((v) => v.retailer_id === r.id && v.ended_at === null)
            return (
              <li key={r.id}>
                <Link to={`/salesman/retailers/${r.id}`}
                  className="flex h-full items-start gap-3 rounded-2xl bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/5 transition hover:ring-leaf-300 active:bg-gray-50">
                  <Avatar name={r.shop_name} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="truncate text-[16px] font-semibold text-ink">{r.shop_name}</p>
                      {open && <span className="shrink-0 rounded-full bg-mango-100 px-2 py-0.5 text-[12px] font-semibold text-mango-600">In visit</span>}
                    </div>
                    <p className="text-[14px] text-ink-soft">{r.owner_name} · Shop +91 {r.phone}</p>
                    {r.registered_mobiles.length > 0 && (
                      <p className="text-[13px] text-ink-soft">Login mobile {r.registered_mobiles.map((m) => `+91 ${m}`).join(', ')}</p>
                    )}
                    <p className="truncate text-[13px] text-ink-soft">{r.address}, {r.city}</p>
                    <p className="mt-1 text-[12px] font-medium text-ink-soft">{r.last_order_at ? `Last order ${ago(r.last_order_at)}` : 'No orders yet'}</p>
                  </div>
                  <Icon name="chevronRight" className="mt-1 h-4 w-4 shrink-0 text-gray-300" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Screen>
  )
}
