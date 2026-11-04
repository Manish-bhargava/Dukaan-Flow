import { useState } from 'react'
import { approveOrder, correctOrderItem, getOrder, holdOrder, rejectOrder, type Order, type OrderItem } from '../../api/orders'
import { ApiError } from '../../api/client'
import { fetchProducts } from '../../api/products'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { OrderLines } from '../../components/OrderLines'
import { Button, ErrorBox, Loading, Notice, SourceBadge, StatusBadge } from '../../components/ui'
import { dateTime, qty } from '../../format'
import { TotalsTable } from '../retailer/CartPage'

const OPEN = ['PENDING', 'CREDIT_HOLD', 'ON_HOLD']

export function DeskOrderPage({ orderId }: { orderId: string }) {
  const order = useLoad((t, s) => getOrder(t, orderId, s), orderId)
  const [editing, setEditing] = useState<string | null>(null)

  if (order.state.status === 'error') return <ErrorBox message={order.state.message} onRetry={order.reload} />
  if (order.state.status === 'loading') return <Loading label="Loading order…" />
  const o = order.state.data
  const open = OPEN.includes(o.status)
  const update = (next: Order) => {
    order.setData(next)
    setEditing(null)
  }

  return (
    <>
      <Link to="/home" className="text-sm font-bold text-leaf-700">← Orders</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-ink">{o.order_number}</h1>
          <p className="flex items-center gap-2 text-sm text-ink-soft">
            Placed {dateTime(o.created_at)} · <SourceBadge source={o.source} />
          </p>
        </div>
        <StatusBadge status={o.status} />
      </div>

      <div className="mt-4 grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {o.ai && (
            <Notice tone="warn">
              <p className="font-bold">Captured by AI from the retailer’s message:</p>
              <p className="mt-1">“{o.ai.original_message}”</p>
            </Notice>
          )}
          {o.remarks && <Notice>Retailer note: {o.remarks}</Notice>}
          {o.status === 'ON_HOLD' && o.hold_reason && <Notice tone="warn">On hold: {o.hold_reason}</Notice>}
          {o.status === 'CREDIT_HOLD' && <Notice tone="warn">This order is above the retailer’s available credit. Confirming it needs a reason.</Notice>}
          {o.status === 'REJECTED' && <Notice>Rejected: {o.rejection_reason}</Notice>}

          <OrderLines
            order={o}
            actions={(item) =>
              !open ? null : editing === item.id ? (
                <CorrectionForm order={o} item={item} onDone={update} onCancel={() => setEditing(null)} />
              ) : (
                <button type="button" onClick={() => setEditing(item.id)} className="mt-2 min-h-10 text-sm font-bold text-leaf-700 underline">
                  Correct this line
                </button>
              )
            }
          />
        </div>

        <aside className="h-fit space-y-4">
          <section className="rounded-xl border border-gray-200 p-4 text-sm">
            <h2 className="font-extrabold text-ink">{o.retailer.shop_name}</h2>
            <p className="text-ink-soft">{o.retailer.owner_name}</p>
            <p className="mt-2 text-ink">{o.retailer.address}, {o.retailer.city}</p>
            <p className="mt-1">
              <a href={`tel:+91${o.retailer.phone}`} className="font-bold text-leaf-700">+91 {o.retailer.phone}</a>
            </p>
            <p className="mt-1 text-ink-soft">GSTIN: {o.retailer.gstin ?? 'not registered'}</p>
          </section>
          <section className="rounded-xl border border-gray-200 p-4">
            <h2 className="font-extrabold text-ink">Total</h2>
            <TotalsTable totals={o} />
          </section>
          {open && <DeskActions order={o} onDone={update} onRefresh={order.reload} />}
          {o.status === 'APPROVED' && o.approved_at && <Notice tone="success">Confirmed {dateTime(o.approved_at)}. Stock and credit updated; included in the Tally export.</Notice>}
        </aside>
      </div>
    </>
  )
}

function CorrectionForm({ order, item, onDone, onCancel }: { order: Order; item: OrderItem; onDone: (o: Order) => void; onCancel: () => void }) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const catalogue = useLoad((t, s) => fetchProducts(t, { retailer_id: order.retailer.id, limit: 100 }, s), `catalogue-${order.retailer.id}`)
  const [productId, setProductId] = useState(item.product_id)
  const [quantity, setQuantity] = useState(String(Number(item.paid_quantity)))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    setBusy(true)
    setError('')
    try {
      const body: { new_product_id?: string; new_quantity?: number; reason?: string } = { reason: reason.trim() || undefined }
      if (productId !== item.product_id) body.new_product_id = productId
      if (Number(quantity) !== Number(item.paid_quantity)) body.new_quantity = Number(quantity)
      onDone((await correctOrderItem(token, order.id, item.id, body)).data)
    } catch (err) {
      setError(toMessage(err))
      setBusy(false)
    }
  }

  const products = catalogue.state.status === 'ready' ? catalogue.state.data.items : []
  const valid = /^\d+$/.test(quantity) && Number(quantity) > 0
  return (
    <div className="mt-3 space-y-3 rounded-lg bg-gray-50 p-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="block text-xs font-bold text-ink-soft">
          Product
          <select value={productId} onChange={(e) => setProductId(e.target.value)} className="mt-1 block min-h-11 w-full rounded-lg border border-gray-300 bg-white px-2 text-sm text-ink">
            {products.length === 0 && <option value={item.product_id}>{item.product_name}</option>}
            {products.map((p) => (
              <option key={p.id} value={p.id}>{`${p.name} (${p.sku}) · ${qty(p.stock_cases)} in stock`}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-bold text-ink-soft">
          Cases
          <input inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value.replace(/\D/g, '').slice(0, 5))} className="mt-1 block min-h-11 w-24 rounded-lg border border-gray-300 px-2 text-sm text-ink" />
        </label>
      </div>
      <label className="block text-xs font-bold text-ink-soft">
        Reason (recorded)
        <input value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Retailer phoned to change quantity" className="mt-1 block min-h-11 w-full rounded-lg border border-gray-300 px-2 text-sm text-ink" />
      </label>
      {error && <ErrorBox message={error} />}
      <div className="flex gap-2">
        <Button busy={busy} disabled={!valid} onClick={save}>Save correction</Button>
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
      <p className="text-xs text-ink-soft">The line is re-priced with the prices and schemes that applied when the order was placed.</p>
    </div>
  )
}

type Action = 'approve' | 'hold' | 'reject'

function DeskActions({ order, onDone, onRefresh }: { order: Order; onDone: (o: Order) => void; onRefresh: () => void }) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [action, setAction] = useState<Action | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [overCredit, setOverCredit] = useState(false) // approval refused for credit: needs a reason
  const needsReason = action === 'hold' || action === 'reject' || (action === 'approve' && (order.status === 'CREDIT_HOLD' || overCredit))

  async function submit() {
    if (!action) return
    setBusy(true)
    setError('')
    try {
      const run = { approve: () => approveOrder(token, order.id, reason.trim()), hold: () => holdOrder(token, order.id, reason.trim()), reject: () => rejectOrder(token, order.id, reason.trim()) }[action]
      onDone((await run()).data)
      setAction(null)
      setReason('')
    } catch (err) {
      if (err instanceof ApiError && err.code === 'CREDIT_LIMIT_EXCEEDED') setOverCredit(true)
      setError(toMessage(err))
      onRefresh() // e.g. a refused approval may have moved the order to credit hold
    } finally {
      setBusy(false)
    }
  }

  const labels: Record<Action, string> = { approve: 'Confirm order', hold: 'Put on hold', reject: 'Reject order' }
  const reasonLabel: Record<Action, string> = {
    approve: 'Why release this order above the credit limit?',
    hold: 'Why is it on hold?',
    reject: 'Reason for rejection (the retailer sees this)',
  }

  return (
    <section className="rounded-xl border border-gray-200 p-4">
      <h2 className="font-extrabold text-ink">Decision</h2>
      <div className="mt-3 grid gap-2">
        {(['approve', 'hold', 'reject'] as Action[])
          .filter((a) => !(a === 'hold' && order.status === 'ON_HOLD'))
          .map((a) => (
            <Button
              key={a}
              variant={a === 'approve' ? 'primary' : a === 'reject' ? 'danger' : 'secondary'}
              onClick={() => {
                setAction(a)
                setError('')
              }}
              className={action === a ? 'ring-2 ring-mango-400' : ''}
            >
              {labels[a]}
            </Button>
          ))}
      </div>
      {action && (
        <div className="mt-3 space-y-2">
          {needsReason && (
            <label className="block text-xs font-bold text-ink-soft">
              {reasonLabel[action]}
              <textarea rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} className="mt-1 block w-full rounded-lg border border-gray-300 p-2 text-sm text-ink" />
            </label>
          )}
          {action === 'approve' && <p className="text-xs text-ink-soft">Stock and credit are checked again; stock is deducted and the order total is added to the retailer’s outstanding.</p>}
          {error && <ErrorBox message={error} />}
          <Button className="w-full" busy={busy} disabled={needsReason && !reason.trim()} onClick={submit}>
            {labels[action]}
          </Button>
        </div>
      )}
    </section>
  )
}
