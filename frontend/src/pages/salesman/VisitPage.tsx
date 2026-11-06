import { useMemo, useState } from 'react'
import type { BundleProduct } from '../../api/salesman'
import { Link } from '../../components/Link'
import { PackShot } from '../../components/PackShot'
import { QtyStepper } from '../../components/ui'
import { ago, gstLabel, offerHeadline, plural, rupees } from '../../format'
import { navigate } from '../../router'
import { useSalesman } from '../../salesman/SalesmanContext'
import { useVisitCart } from '../../salesman/visitCart'
import { EmptyState, Icon, PrimaryButton, Screen, SearchField } from '../../salesman/ui'

/** The dedicated visit screen: pick products for this shop during an open visit. */
export function VisitPage({ retailerId }: { retailerId: string }) {
  const { bundle, visits, endVisit } = useSalesman()
  const retailer = bundle?.retailers.find((r) => r.id === retailerId)
  const visit = visits.find((v) => v.retailer_id === retailerId && v.ended_at === null)
  const { cart, setQty } = useVisitCart(visit?.id)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const prices = useMemo(() => bundle?.prices[retailerId] ?? {}, [bundle, retailerId])
  const products = useMemo(() => (bundle?.products ?? []).filter((p) => prices[p.id]), [bundle, prices])

  const back = { to: `/salesman/retailers/${retailerId}`, label: 'Shop' }
  if (!bundle || !retailer) {
    return <Screen title="Visit" back={{ to: '/salesman/retailers', label: 'Retailers' }}><EmptyState icon="store" title="Retailer not found" /></Screen>
  }
  if (!visit) {
    return (
      <Screen title={retailer.shop_name} back={back}>
        <EmptyState icon="clock" title="No visit in progress">Start a visit from the shop page to take an order.</EmptyState>
      </Screen>
    )
  }

  const q = search.trim().toLowerCase()
  const shown = products.filter((p) => (!category || p.category.id === category) && (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)))
  const lines = products.filter((p) => cart[p.id] > 0)
  const cases = lines.reduce((s, p) => s + cart[p.id], 0)

  async function endWithoutOrder() {
    if (!window.confirm(`End the visit at ${retailer!.shop_name} without an order?`)) return
    await endVisit(visit!.id, 'NO_ORDER')
    navigate(`/salesman/retailers/${retailerId}`)
  }

  return (
    <Screen title={retailer.shop_name} subtitle={<span className="inline-flex items-center gap-1"><Icon name="clock" className="h-4 w-4" /> Visit started {ago(visit.started_at)}</span>} back={back}>
      <div className="space-y-3">
        <div className="max-w-xl"><SearchField value={search} onChange={setSearch} placeholder="Search product or SKU" /></div>
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          {[{ id: '', name: 'All' }, ...bundle.categories].map((c) => (
            <button key={c.id} type="button" onClick={() => setCategory(c.id)}
              className={`min-h-9 shrink-0 rounded-full px-4 text-[14px] font-semibold ring-1 transition ${category === c.id ? 'bg-leaf-700 text-white ring-leaf-700' : 'bg-white text-ink ring-black/10'}`}>
              {c.name}
            </button>
          ))}
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState icon="search" title="No products found" />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((p) => (
            <ProductCard key={p.id} product={p} price={prices[p.id].case_price} gst={gstLabel(p.gst_rate, prices[p.id].tax_inclusive)}
              qty={cart[p.id] ?? 0} onChange={(n) => setQty(p.id, n)} />
          ))}
        </ul>
      )}

      <div className="max-w-sm"><PrimaryButton tone="danger" onClick={() => void endWithoutOrder()}>End visit — no order</PrimaryButton></div>

      {lines.length > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-2">
          <Link to={`/salesman/visit/${retailerId}/review`}
            className="mx-auto flex min-h-[56px] max-w-3xl items-center justify-between gap-3 rounded-2xl bg-leaf-700 px-5 text-white shadow-lg shadow-leaf-900/20 active:bg-leaf-800">
            <span className="text-[15px] font-semibold">{plural(lines.length, 'product')} · {plural(cases, 'case')}</span>
            <span className="flex items-center gap-1 text-[16px] font-bold">Review order <Icon name="chevronRight" className="h-5 w-5" /></span>
          </Link>
        </div>
      )}
    </Screen>
  )
}

function ProductCard({ product: p, price, gst, qty, onChange }: { product: BundleProduct; price: string; gst: string; qty: number; onChange: (n: number) => void }) {
  return (
    <li className={`flex flex-col justify-between rounded-2xl bg-white p-3 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ${qty > 0 ? 'ring-leaf-300' : 'ring-black/5'}`}>
      <div className="flex items-center gap-3">
        <div className="h-16 w-16 shrink-0 rounded-xl bg-[#f4f5f2] p-1">
          <PackShot name={p.name} brand={p.brand} category={p.category.name} packSize={p.pack_size} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold leading-snug text-ink">{p.name}</p>
          <p className="text-[13px] text-ink-soft">{rupees(price)} / {p.order_unit} · {gst}</p>
          <p className={`text-[12px] font-medium ${p.in_stock ? 'text-leaf-700' : 'text-red-700'}`}>{p.in_stock ? `${plural(p.stock_cases, p.order_unit)} in stock` : 'Out of stock'}</p>
          {p.schemes.map((s) => (
            <span key={s.id} className="mt-1 inline-block rounded-md bg-mango-100 px-1.5 py-0.5 text-[12px] font-semibold text-mango-600">{offerHeadline(s, p.order_unit)}</span>
          ))}
        </div>
        {qty === 0 && (
          <button type="button" disabled={!p.in_stock} onClick={() => onChange(1)}
            className="min-h-10 shrink-0 rounded-full bg-leaf-50 px-4 text-[15px] font-semibold text-leaf-700 ring-1 ring-leaf-200 active:bg-leaf-100 disabled:bg-gray-100 disabled:text-gray-400 disabled:ring-0">
            {p.in_stock ? 'Add' : 'None'}
          </button>
        )}
      </div>
      {qty > 0 && (
        <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
          <span className="text-[14px] font-semibold text-leaf-700">In this order</span>
          <QtyStepper label={p.name} value={qty} onChange={onChange} />
        </div>
      )}
    </li>
  )
}
