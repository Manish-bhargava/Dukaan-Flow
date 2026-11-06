import { useState } from 'react'
import { fetchDispatch, fetchSalesmen, type ProductTotal } from '../../api/orderDesk'
import { useLoad } from '../../auth/useApi'
import { Icon } from '../../components/Icon'
import { Link } from '../../components/Link'
import { Button, Empty, ErrorBox, Loading } from '../../components/ui'
import { qty, rupees } from '../../format'
import { PageHeader } from './deskUi'

const todayIst = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
const field = 'mt-1 block min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm text-ink'

/** Dispatch preparation: consolidated quantities of confirmed orders and a loading list per
 *  salesman beat (V1 records no routes or vans; each shop's salesman is its beat). */
export function DispatchPage() {
  const [from, setFrom] = useState(todayIst)
  const [to, setTo] = useState(todayIst)
  const [salesman, setSalesman] = useState('')
  const salesmen = useLoad((t, s) => fetchSalesmen(t, s), 'salesmen')
  const data = useLoad((t, s) => fetchDispatch(t, { from_date: from || undefined, to_date: to || undefined, salesman_id: salesman || undefined }, s),
    `${from}|${to}|${salesman}`)

  return (
    <>
      <PageHeader title="Dispatch preparation" subtitle="Confirmed orders to load: total cases per product (paid + free) and stops per beat."
        actions={<Button variant="secondary" onClick={() => window.print()}><Icon name="print" className="h-4 w-4" /> Print loading list</Button>} />
      <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-gray-200 bg-gray-50/60 p-3 sm:grid-cols-3 print:hidden">
        <label className="text-xs font-bold text-ink-soft">Confirmed from<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={field} /></label>
        <label className="text-xs font-bold text-ink-soft">to<input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={field} /></label>
        <label className="col-span-2 text-xs font-bold text-ink-soft sm:col-span-1">Salesman beat
          <select value={salesman} onChange={(e) => setSalesman(e.target.value)} className={field}>
            <option value="">All beats</option>
            {salesmen.state.status === 'ready' && salesmen.state.data.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      </div>
      <p className="mt-3 hidden text-sm print:block">Confirmed {from || '…'} to {to || '…'}</p>

      <div className="mt-5">
        {data.state.status === 'error' ? <ErrorBox message={data.state.message} onRetry={data.reload} />
          : data.state.status === 'loading' ? <Loading label="Preparing loading list…" />
          : data.state.data.order_count === 0 ? <Empty title="No confirmed orders">No orders were confirmed in these dates.</Empty>
          : (
            <div className={`space-y-8 ${data.loading ? 'opacity-60' : ''}`}>
              <section>
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <h2 className="text-lg font-extrabold text-ink">Consolidated quantities</h2>
                  <p className="text-sm text-ink-soft">{data.state.data.order_count} orders · {rupees(data.state.data.grand_total)}</p>
                </div>
                <ProductTable rows={data.state.data.products} />
              </section>

              {data.state.data.beats.map((beat) => (
                <section key={beat.salesman?.id ?? 'none'} className="break-inside-avoid rounded-2xl border border-gray-200 p-4 print:break-before-page">
                  <div className="flex flex-wrap items-end justify-between gap-2">
                    <div>
                      <h2 className="flex items-center gap-2 text-lg font-extrabold text-ink"><Icon name="truck" className="h-5 w-5 text-leaf-700" />
                        {beat.salesman ? `${beat.salesman.name}’s beat` : 'Shops without a salesman'}</h2>
                      {beat.salesman && <p className="text-sm text-ink-soft">+91 {beat.salesman.phone}</p>}
                    </div>
                    <p className="text-sm text-ink-soft">{beat.stops.length} {beat.stops.length === 1 ? 'shop' : 'shops'} · {beat.orders_count} orders · {rupees(beat.grand_total)}</p>
                  </div>
                  <ProductTable rows={beat.products} compact />
                  <h3 className="mt-4 text-sm font-bold uppercase tracking-wide text-ink-soft">Stops</h3>
                  <ol className="mt-2 grid gap-2 lg:grid-cols-2">
                    {beat.stops.map((s, i) => (
                      <li key={s.retailer_id} className="break-inside-avoid rounded-xl bg-gray-50 p-3 text-sm">
                        <p className="font-bold text-ink">{i + 1}. {s.shop_name}</p>
                        <p className="text-ink-soft">{s.owner_name} · +91 {s.phone}</p>
                        <p className="text-ink-soft">{s.address}, {s.city}</p>
                        <ul className="mt-2 space-y-0.5">
                          {s.products.map((it) => (
                            <li key={it.product_id} className="flex justify-between gap-2">
                              <span className="text-ink">{it.name}</span>
                              <span className="shrink-0 font-semibold text-ink">{qty(it.paid)}{Number(it.free) > 0 ? ` + ${qty(it.free)} free` : ''} {it.order_unit}{Number(it.total) === 1 ? '' : 's'}</span>
                            </li>
                          ))}
                        </ul>
                        <div className="mt-2 flex flex-wrap items-end justify-between gap-2 border-t border-gray-200 pt-2 text-xs">
                          <span className="flex flex-wrap gap-x-2">
                            {s.orders.map((o) => <Link key={o.order_id} to={`/desk/orders/${o.order_id}`} className="font-bold text-leaf-700">{o.order_number}</Link>)}
                          </span>
                          <span className="font-bold text-ink">{rupees(s.grand_total)}</span>
                        </div>
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
          )}
      </div>
    </>
  )
}

function ProductTable({ rows, compact = false }: { rows: ProductTotal[]; compact?: boolean }) {
  return (
    <div className={`mt-3 overflow-x-auto ${compact ? '' : 'rounded-2xl border border-gray-200'}`}>
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead className={`text-xs uppercase tracking-wide text-ink-soft ${compact ? 'border-b border-gray-200' : 'bg-gray-50'}`}>
          <tr>
            <th className="py-2 pl-3 pr-3">Product</th>
            <th className="py-2 pr-3">Pack</th>
            <th className="py-2 pr-3 text-right">Ordered</th>
            <th className="py-2 pr-3 text-right">Free</th>
            <th className="py-2 pr-3 text-right">To load</th>
            <th className="py-2 pr-3 text-right">Orders</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((p) => (
            <tr key={p.product_id}>
              <td className="py-2 pl-3 pr-3"><span className="font-semibold text-ink">{p.name}</span><span className="block text-xs text-ink-soft">{p.sku}</span></td>
              <td className="py-2 pr-3 text-ink-soft">{p.pack_size}</td>
              <td className="py-2 pr-3 text-right">{qty(p.paid)}</td>
              <td className="py-2 pr-3 text-right">{Number(p.free) > 0 ? qty(p.free) : '—'}</td>
              <td className="py-2 pr-3 text-right font-extrabold text-ink">{qty(p.total)} {p.order_unit}{Number(p.total) === 1 ? '' : 's'}</td>
              <td className="py-2 pr-3 text-right text-ink-soft">{p.orders}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
