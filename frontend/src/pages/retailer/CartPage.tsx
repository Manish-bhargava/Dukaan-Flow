import { useEffect, useState, type ReactNode } from 'react'
import { confirmExtraction } from '../../api/aiOrders'
import { placeOrder, quoteCart, type CartItemInput, type QuoteLine, type Totals } from '../../api/orders'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { useCart, type CartLine } from '../../cart/CartContext'
import { Link } from '../../components/Link'
import { Button, Empty, ErrorBox, Notice, QtyStepper } from '../../components/ui'
import { gstLabel, plural, qty, rupees } from '../../format'
import { navigate } from '../../router'

export function CartPage() {
  const cart = useCart()
  const token = useToken()
  const toMessage = useErrorMessage()
  const [remarks, setRemarks] = useState('')
  const [placing, setPlacing] = useState(false)
  const [placeError, setPlaceError] = useState('')

  const items: CartItemInput[] = cart.lines.map((l) => ({ product_id: l.product_id, quantity: l.quantity, unit: l.order_unit }))
  const cartKey = items.map((i) => `${i.product_id}:${i.quantity}:${i.unit}`).join(',')

  // Re-price shortly after the last quantity change (fewer requests on slow connections).
  const [pricedKey, setPricedKey] = useState(cartKey)
  useEffect(() => {
    const timer = window.setTimeout(() => setPricedKey(cartKey), 400)
    return () => window.clearTimeout(timer)
  }, [cartKey])
  const quote = useLoad(
    (t, s) => (pricedKey ? quoteCart(t, parseKey(pricedKey), s) : Promise.resolve({ success: true as const, message: '', data: null })),
    pricedKey,
  )
  const priced = quote.state.status === 'ready' ? quote.state.data : null
  const upToDate = pricedKey === cartKey && !quote.loading && priced !== null

  if (cart.lines.length === 0) {
    return (
      <>
        <h1 className="text-xl font-extrabold text-ink">Cart</h1>
        <div className="mt-4">
          <Empty title="Your cart is empty">
            Add products from the <Link to="/home" className="font-bold text-leaf-700 underline">catalogue</Link> or{' '}
            <Link to="/ai-order" className="font-bold text-leaf-700 underline">type your order as a message</Link>.
          </Empty>
        </div>
      </>
    )
  }

  async function place() {
    setPlacing(true)
    setPlaceError('')
    try {
      const ai = cart.ai
      const order = ai
        ? (await confirmExtraction(token, ai.extractionId, items.map((i) => ({ ...i, extraction_item_id: ai.itemByProduct[i.product_id] ?? null })), remarks)).data
        : (await placeOrder(token, items, remarks)).data
      cart.clear()
      navigate(`/orders/${order.id}?placed=1`)
    } catch (err) {
      setPlaceError(toMessage(err))
      setPlacing(false)
      quote.reload()
    }
  }

  const byProduct = new Map((priced?.lines ?? []).map((l) => [l.product_id, l]))
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-extrabold text-ink">Cart</h1>
        <button type="button" onClick={cart.clear} className="min-h-11 px-2 text-sm font-bold text-red-700">
          Empty cart
        </button>
      </div>
      {cart.ai && <p className="mt-1 text-sm text-ink-soft">Includes items read from your message.</p>}

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <ul className="divide-y divide-gray-200 border-y border-gray-200">
          {cart.lines.map((line) => (
            <CartRow key={line.product_id} line={line} priced={byProduct.get(line.product_id)} stale={!upToDate} onChange={(n) => cart.setQuantity(line, n)} />
          ))}
        </ul>

        <aside className="h-fit rounded-xl border border-gray-200 p-4 lg:sticky lg:top-32">
          <h2 className="font-extrabold text-ink">Order summary</h2>
          {quote.state.status === 'error' ? (
            <div className="mt-3">
              <ErrorBox message={quote.state.message} onRetry={quote.reload} />
            </div>
          ) : priced ? (
            <TotalsTable totals={priced.totals} faded={!upToDate} />
          ) : (
            <p className="mt-3 text-sm text-ink-soft">Calculating…</p>
          )}
          {priced && !priced.can_order && upToDate && (
            <div className="mt-3">
              <Notice tone="warn">Some items are not available in the quantity you want. Reduce or remove them to place the order.</Notice>
            </div>
          )}
          <label htmlFor="remarks" className="mt-4 block text-sm font-bold text-ink">
            Note for the distributor (optional)
          </label>
          <textarea
            id="remarks"
            rows={2}
            maxLength={500}
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            className="mt-1 w-full rounded-lg border border-gray-300 p-2 text-base outline-none focus:border-leaf-600"
            placeholder="e.g. Deliver before 10 am"
          />
          {placeError && (
            <div className="mt-3">
              <ErrorBox message={placeError} />
            </div>
          )}
          <Button className="mt-3 w-full" busy={placing} disabled={!upToDate || !priced?.can_order} onClick={place}>
            Place order{priced && upToDate ? ` · ${rupees(priced.totals.grand_total)}` : ''}
          </Button>
          <p className="mt-2 text-xs text-ink-soft">Prices, schemes and GST are calculated by DukaanFlow and checked again when you place the order. No payment is taken now.</p>
        </aside>
      </div>
    </>
  )
}

function parseKey(key: string): CartItemInput[] {
  return key.split(',').map((part) => {
    const [product_id, quantity, unit] = part.split(':')
    return { product_id, quantity: Number(quantity), unit }
  })
}

function CartRow({ line, priced, stale, onChange }: { line: CartLine; priced?: QuoteLine; stale: boolean; onChange: (n: number) => void }) {
  return (
    <li className="py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-bold text-ink">{line.name}</p>
          <p className="text-xs text-ink-soft">
            {line.sku} · {line.pack_size}
          </p>
        </div>
        <p className={`shrink-0 text-right text-lg font-extrabold ${stale ? 'text-ink-soft' : 'text-ink'}`}>{priced ? rupees(priced.line_total) : '—'}</p>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <QtyStepper label={line.name} value={line.quantity} onChange={onChange} />
        <button type="button" onClick={() => onChange(0)} className="min-h-11 px-2 text-sm font-bold text-ink-soft hover:text-red-700">
          Remove
        </button>
      </div>
      {priced && (
        <dl className={`mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4 ${stale ? 'opacity-50' : ''}`}>
          <Field label="Rate">
            {rupees(priced.unit_price)} / {priced.price_basis === 'PIECE' ? 'piece' : priced.order_unit}
          </Field>
          <Field label="GST">{gstLabel(priced.gst_rate, priced.tax_inclusive)}</Field>
          <Field label="Discount">{Number(priced.discount_amount) > 0 ? `${qty(priced.discount_percentage)}% · −${rupees(priced.discount_amount)}` : '—'}</Field>
          <Field label="Free">{Number(priced.free_quantity) > 0 ? plural(priced.free_quantity, priced.order_unit) : '—'}</Field>
        </dl>
      )}
      {priced?.scheme && (
        <p className="mt-2 text-sm font-bold text-mango-600">
          Scheme applied: {priced.scheme.description}
          {Number(priced.free_quantity) > 0 && ` · you get ${plural(Number(priced.quantity) + Number(priced.free_quantity), priced.order_unit)}`}
        </p>
      )}
      {priced && !priced.stock_ok && !stale && (
        <p className="mt-2 text-sm font-bold text-red-700">
          Only {plural(priced.available_stock, priced.order_unit)} available
          {Number(priced.free_quantity) > 0 ? ' (free cases count too)' : ''}.
        </p>
      )}
    </li>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="font-semibold text-ink">{children}</dd>
    </div>
  )
}

export function TotalsTable({ totals, faded = false }: { totals: Totals; faded?: boolean }) {
  const rows: [string, string][] = [
    ['Value before discount', rupees(totals.subtotal)],
    ['Scheme discount', Number(totals.discount_total) > 0 ? `−${rupees(totals.discount_total)}` : rupees(0)],
    ['Taxable value', rupees(totals.taxable_amount)],
    ['GST', rupees(totals.gst_amount)],
  ]
  return (
    <dl className={`mt-3 space-y-1.5 text-sm ${faded ? 'opacity-50' : ''}`}>
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between">
          <dt className="text-ink-soft">{label}</dt>
          <dd className="font-semibold text-ink">{value}</dd>
        </div>
      ))}
      <div className="flex justify-between border-t border-gray-200 pt-2 text-base">
        <dt className="font-extrabold text-ink">Order total</dt>
        <dd className="font-extrabold text-ink">{rupees(totals.grand_total)}</dd>
      </div>
    </dl>
  )
}
