import { useEffect, useMemo, useState } from 'react'
import { quoteCart, type Quote } from '../../api/orders'
import { useToken } from '../../auth/useApi'
import { QtyStepper } from '../../components/ui'
import { offerHeadline, plural, rupees } from '../../format'
import { navigate } from '../../router'
import { useSalesman } from '../../salesman/SalesmanContext'
import { clearVisitCart, useVisitCart } from '../../salesman/visitCart'
import { Card, EmptyState, Icon, PrimaryButton, Screen, SectionLabel } from '../../salesman/ui'

/** Review and submit the visit's order. Online: priced by the backend. Offline: an estimate,
 *  and the order is saved on the phone to sync later. */
export function VisitReviewPage({ retailerId }: { retailerId: string }) {
  const { bundle, visits, online, saveOrder, endVisit } = useSalesman()
  const token = useToken()
  const retailer = bundle?.retailers.find((r) => r.id === retailerId)
  const visit = visits.find((v) => v.retailer_id === retailerId && v.ended_at === null)
  const { cart, setQty } = useVisitCart(visit?.id)
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const [quote, setQuote] = useState<Quote | null>(null)
  const prices = useMemo(() => bundle?.prices[retailerId] ?? {}, [bundle, retailerId])
  const lines = (bundle?.products ?? []).filter((p) => prices[p.id] && cart[p.id] > 0)
  const key = lines.map((p) => `${p.id}:${cart[p.id]}`).join(',')

  useEffect(() => {
    if (!online || !token || lines.length === 0) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      quoteCart(token, lines.map((p) => ({ product_id: p.id, quantity: cart[p.id], unit: p.order_unit })), controller.signal, retailerId)
        .then((r) => setQuote(r.data))
        .catch(() => setQuote(null))
    }, 300)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, key, token, retailerId])

  const back = { to: `/salesman/visit/${retailerId}`, label: 'Products' }
  if (!retailer || !visit) {
    return <Screen title="Review order" back={{ to: `/salesman/retailers/${retailerId}`, label: 'Shop' }}><EmptyState icon="clock" title="No visit in progress" /></Screen>
  }
  if (lines.length === 0) {
    return <Screen title="Review order" back={back}><EmptyState icon="cart" title="No products added yet">Go back and add products for this shop.</EmptyState></Screen>
  }

  const estimate = lines.reduce((s, p) => s + cart[p.id] * Number(prices[p.id].case_price), 0)
  const priced = online && quote && quote.lines.length === lines.length ? quote : null
  const overCredit = priced ? !priced.within_credit : estimate > Number(retailer.credit?.available_credit ?? 0)

  async function submit() {
    setBusy(true)
    const order = await saveOrder({
      retailer_id: retailer!.id,
      shop_name: retailer!.shop_name,
      remarks: remarks.trim() || null,
      items: lines.map((p) => ({
        product_id: p.id, sku: p.sku, name: p.name, pack_size: p.pack_size, order_unit: p.order_unit, quantity: cart[p.id],
        expected_unit_price: prices[p.id].dealer_price, price_basis: prices[p.id].price_basis, case_price: prices[p.id].case_price,
        schemes: p.schemes.map((sch) => ({ id: sch.id, description: sch.description })),
      })),
    })
    await endVisit(visit!.id, 'ORDER_PLACED', order.client_order_id)
    clearVisitCart(visit!.id)
    navigate(`/salesman/orders/local/${order.client_order_id}`)
  }

  return (
    <Screen title="Review order" subtitle={retailer.shop_name} back={back}>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div>
        <SectionLabel>{plural(lines.length, 'product')}</SectionLabel>
        <ul className="divide-y divide-gray-100 overflow-hidden rounded-2xl bg-white ring-1 ring-black/5">
          {lines.map((p) => {
            const line = priced?.lines.find((l) => l.product_id === p.id)
            return (
              <li key={p.id} className="space-y-2 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[15px] font-semibold text-ink">{p.name}</p>
                    <p className="text-[13px] text-ink-soft">{rupees(prices[p.id].case_price)} / {p.order_unit}</p>
                  </div>
                  <p className="shrink-0 text-[15px] font-bold text-ink">{line ? rupees(line.line_total) : `≈ ${rupees(cart[p.id] * Number(prices[p.id].case_price))}`}</p>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <QtyStepper label={p.name} value={cart[p.id]} onChange={(n) => setQty(p.id, n)} />
                  {line?.scheme ? (
                    <span className="text-[13px] font-semibold text-mango-600">{line.scheme.description}{Number(line.free_quantity) > 0 ? ` · +${plural(line.free_quantity, p.order_unit)} free` : ''}</span>
                  ) : p.schemes.length > 0 && !line ? (
                    <span className="text-[12px] font-semibold text-mango-600">{p.schemes.map((s) => offerHeadline(s, p.order_unit)).join(' · ')}</span>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ul>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-36">
      <Card>
        {priced ? (
          <dl className="space-y-1.5 text-[15px]">
            <div className="flex justify-between"><dt className="text-ink-soft">Taxable value</dt><dd className="font-semibold">{rupees(priced.totals.taxable_amount)}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-soft">GST</dt><dd className="font-semibold">{rupees(priced.totals.gst_amount)}</dd></div>
            <div className="flex justify-between border-t border-gray-100 pt-2 text-[17px]"><dt className="font-bold">Order total</dt><dd className="font-extrabold">{rupees(priced.totals.grand_total)}</dd></div>
          </dl>
        ) : (
          <>
            <div className="flex justify-between text-[17px]"><span className="font-bold">Estimate</span><b>≈ {rupees(estimate)}</b></div>
            <p className="mt-1 text-[13px] text-ink-soft">
              {online ? 'Calculating…' : 'Offline estimate (price × cases, before schemes and GST). The final amount is calculated when the order syncs.'}
            </p>
          </>
        )}
      </Card>

      {overCredit && (
        <div className="flex gap-3 rounded-2xl bg-orange-50 p-4 text-[14px] text-orange-900 ring-1 ring-orange-200">
          <Icon name="alert" className="h-5 w-5 shrink-0" /> Above the shop’s available credit: the order will go to the order desk for credit approval.
        </div>
      )}
      {!online && (
        <div className="flex gap-3 rounded-2xl bg-gray-800 p-4 text-[14px] text-white">
          <Icon name="cloudOff" className="h-5 w-5 shrink-0" /> You are offline. The order is saved on this phone and sent automatically when internet is back.
        </div>
      )}

      <label className="block">
        <span className="px-1 text-[13px] font-semibold uppercase tracking-wide text-ink-soft">Note (optional)</span>
        <textarea rows={2} maxLength={500} value={remarks} onChange={(e) => setRemarks(e.target.value)}
          className="mt-1.5 w-full rounded-2xl bg-white p-3 text-[16px] ring-1 ring-black/5 outline-none focus:ring-2 focus:ring-leaf-500" />
      </label>

      <PrimaryButton busy={busy} onClick={() => void submit()}>{online ? 'Submit order' : 'Save order offline'}</PrimaryButton>
      </aside>
      </div>
    </Screen>
  )
}
