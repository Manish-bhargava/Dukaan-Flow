import { useState, type ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { fetchOrderReview, listDeskOrders, type OrderReview } from '../../api/orderDesk'
import { approveOrder, correctOrderItem, rejectOrder, requestClarification, type Order, type OrderItem } from '../../api/orders'
import { fetchProducts } from '../../api/products'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { OrderLines } from '../../components/OrderLines'
import { Button, ErrorBox, Loading, Notice, SourceBadge, StatusBadge } from '../../components/ui'
import { dateTime, qty, rupees, SOURCE_LABELS } from '../../format'
import { TotalsTable } from '../retailer/CartPage'
import { History, WarningList } from './deskUi'

const OPEN = ['PENDING', 'CREDIT_HOLD', 'ON_HOLD', 'CLARIFICATION_REQUIRED']
const BACK: Record<string, [string, string]> = {
  PENDING: ['/desk/incoming', 'Incoming orders'],
  CREDIT_HOLD: ['/desk/incoming', 'Incoming orders'],
  ON_HOLD: ['/desk/incoming', 'Incoming orders'],
  CLARIFICATION_REQUIRED: ['/desk/clarification', 'Clarification required'],
  APPROVED: ['/desk/confirmed', 'Confirmed orders'],
  REJECTED: ['/desk/rejected', 'Rejected orders'],
}

/** Order review: everything needed to decide, with the actions the order's status allows. */
export function DeskOrderPage({ orderId }: { orderId: string }) {
  const review = useLoad((t, s) => fetchOrderReview(t, orderId, s), orderId)
  const [editing, setEditing] = useState<string | null>(null)
  const [decided, setDecided] = useState<Decided | null>(null)

  if (review.state.status === 'error') return <ErrorBox message={review.state.message} onRetry={review.reload} />
  if (review.state.status === 'loading') return <Loading label="Loading order…" />
  const r = review.state.data
  const o = r.order
  const open = OPEN.includes(o.status)
  const [backTo, backLabel] = BACK[o.status]
  const refresh = () => {
    setEditing(null)
    review.reload()
  }
  const finish = (what: Decided) => {
    setDecided(what)
    refresh()
    window.scrollTo(0, 0)
  }
  const stockFor = (item: OrderItem) => r.stock.find((s) => s.item_id === item.id)

  return (
    <>
      <Link to={backTo} className="text-sm font-bold text-leaf-700 print:hidden">← {backLabel}</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-ink sm:text-2xl">{o.order_number}</h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-ink-soft">
            Placed {dateTime(o.created_at)} · <SourceBadge source={o.source} />
            {o.created_offline && <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-bold">Created offline</span>}
          </p>
        </div>
        <StatusBadge status={o.status} />
      </div>

      {decided && <DecidedBanner what={decided} orderId={o.id} />}
      {open && !decided && <NextSteps hasWarnings={r.warnings.length > 0} />}

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          {open && <div className="lg:hidden"><Decision review={r} onDone={finish} /></div>}
          {open && <WarningList warnings={r.warnings} />}
          <StatusNotice order={o} />
          {o.ai && <AiSource review={r} />}
          {o.remarks && <Notice>Note on the order: {o.remarks}</Notice>}

          <section>
            <h2 className="text-lg font-extrabold text-ink">Products</h2>
            <div className="mt-2">
              <OrderLines
                order={o}
                actions={(item) => {
                  const s = stockFor(item)
                  return (
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                      {s && (
                        <span className={`text-xs font-semibold ${s.ok ? 'text-leaf-700' : 'text-red-700'}`}>
                          {open ? `Needs ${qty(s.needed)} ${item.order_unit}s incl. free · ${qty(s.available)} in stock` : `${qty(s.available)} in stock now`}
                          {item.order_unit !== 'piece' && ` · ${item.pack_size}`}
                        </span>
                      )}
                      {open && editing !== item.id && (
                        <button type="button" onClick={() => setEditing(item.id)} className="min-h-10 text-sm font-bold text-leaf-700 underline">
                          Edit line
                        </button>
                      )}
                      {open && editing === item.id && (
                        <CorrectionForm order={o} item={item} onDone={refresh} onCancel={() => setEditing(null)} />
                      )}
                    </div>
                  )
                }}
              />
            </div>
          </section>

          <section className="rounded-2xl border border-gray-200 p-4">
            <h2 className="mb-3 text-lg font-extrabold text-ink">History</h2>
            <History events={r.history} />
          </section>
        </div>

        <aside className="h-fit space-y-4 lg:sticky lg:top-32">
          {open && <div className="hidden lg:block"><Decision review={r} onDone={finish} /></div>}
          <Card title="Retailer">
            <p className="font-bold text-ink">{o.retailer.shop_name}</p>
            <p className="text-ink-soft">{o.retailer.owner_name}</p>
            <p className="mt-2 text-ink">{o.retailer.address}, {o.retailer.city}</p>
            <p className="mt-1"><a href={`tel:+91${o.retailer.phone}`} className="font-bold text-leaf-700">+91 {o.retailer.phone}</a></p>
            <Rows rows={[['Retailer ID', <span key="id" className="break-all font-mono text-xs">{o.retailer.id}</span>], ['GSTIN', o.retailer.gstin ?? 'not registered']]} />
          </Card>
          <Card title="Order">
            <Rows rows={[
              ['Source', SOURCE_LABELS[o.source]],
              ['Placed by', `${o.created_by.name} (${o.created_by.role === 'SALESMAN' ? 'salesman' : o.created_by.role === 'RETAILER' ? 'retailer' : 'staff'})`],
              ['Salesman', r.salesman ? `${r.salesman.name} · ${r.salesman.phone}` : 'None assigned'],
              ...(o.created_offline && o.client_created_at ? [['Created on phone', dateTime(o.client_created_at)] as [string, ReactNode]] : []),
              ...(o.approved_at ? [['Confirmed', `${dateTime(o.approved_at)}${o.approved_by ? ` by ${o.approved_by.name}` : ''}`] as [string, ReactNode]] : []),
              ...(o.status === 'APPROVED' ? [['Tally', o.tally_exported_at ? `Exported ${dateTime(o.tally_exported_at)}` : 'Not exported yet'] as [string, ReactNode]] : []),
            ]} />
          </Card>
          {r.credit ? (
            <Card title="Credit">
              <Rows rows={[
                ['Credit limit', rupees(r.credit.credit_limit)],
                ['Outstanding', rupees(r.credit.current_outstanding)],
                ['Held by orders under review', rupees(r.credit.reserved_for_review)],
                ['Available now', <span key="available" className={Number(r.credit.available_credit) < Number(o.grand_total) && open ? 'text-red-700' : 'text-leaf-700'}>{rupees(r.credit.available_credit)}</span>],
              ]} />
              {open && o.status !== 'CREDIT_HOLD' && <p className="mt-2 text-xs text-ink-soft">“Held” includes this order while it waits.</p>}
            </Card>
          ) : <Notice tone="warn">This retailer has no credit account.</Notice>}
          <Card title="Total"><TotalsTable totals={o} /></Card>
        </aside>
      </div>
    </>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-gray-200 p-4 text-sm">
      <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-ink-soft">{title}</h2>
      {children}
    </section>
  )
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="mt-2 space-y-1.5">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-3">
          <dt className="shrink-0 text-ink-soft">{label}</dt>
          <dd className="text-right font-semibold text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function StatusNotice({ order: o }: { order: Order }) {
  if (o.status === 'CLARIFICATION_REQUIRED') return <Notice tone="warn"><b>Clarification requested:</b> {o.clarification_message}</Notice>
  if (o.status === 'ON_HOLD' && o.hold_reason && !o.created_offline) return <Notice tone="warn"><b>On hold:</b> {o.hold_reason}</Notice>
  if (o.status === 'CREDIT_HOLD') return <Notice tone="warn">Above the retailer’s available credit. Confirming it needs a credit override reason.</Notice>
  if (o.status === 'REJECTED') return <Notice><b>Rejected:</b> {o.rejection_reason}</Notice>
  if (o.status === 'APPROVED') return <Notice tone="success">Confirmed: stock deducted and the total added to the retailer’s outstanding.</Notice>
  return null
}

const INPUT_LABELS: Record<string, string> = { TEXT: 'text message', IMAGE: 'photo of an order list', VOICE: 'voice note (transcribed)' }

/** How the AI read the retailer's message: recommended product, confidence, evidence and
 *  alternatives per line (business evidence only, no model reasoning). */
function AiSource({ review }: { review: OrderReview }) {
  return (
    <section className="rounded-2xl border border-gray-200 p-4 text-sm">
      <h2 className="font-extrabold text-ink">Captured by AI from a {INPUT_LABELS[review.ai_input_type ?? 'TEXT'] ?? 'message'}</h2>
      <p className="mt-1 whitespace-pre-line rounded-lg bg-gray-50 p-3 text-ink">“{review.order.ai!.original_message}”</p>
      {review.ai_lines.length > 0 && (
        <ul className="mt-3 space-y-3">
          {review.ai_lines.map((l, i) => {
            const pct = Math.round(Number(l.confidence) * 100)
            return (
              <li key={i} className="rounded-xl border border-gray-100 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs text-ink-soft">Retailer wrote “{l.original_text}”</p>
                    <p className="font-bold text-ink">
                      AI recommended: {l.product ? `${l.product.name} (${l.product.sku})` : 'no product'}
                      {l.quantity ? ` · ${qty(l.quantity)} ${l.unit ? `${l.unit}${Number(l.quantity) === 1 ? '' : 's'}` : '(unit not stated)'}` : ' · quantity not stated'}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold ${pct >= 75 ? 'bg-leaf-50 text-leaf-700' : 'bg-mango-100 text-mango-600'}`}>{pct}% confidence</span>
                </div>
                {l.clarification_reason && <p className="mt-1 text-xs font-semibold text-mango-600">Needed clarification: {l.clarification_reason}</p>}
                {l.evidence.length > 0 && (
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-ink">
                    {l.evidence.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                )}
                {l.alternatives.length > 0 && (
                  <p className="mt-2 text-xs text-ink-soft">
                    Alternatives: {l.alternatives.map((a) => {
                      const name = String(a.name ?? a.sku)
                      return a.pack_size && !name.includes(String(a.pack_size)) ? `${name} ${String(a.pack_size)}` : name
                    }).join(' · ')}
                  </p>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-3 text-xs text-ink-soft">The retailer confirmed these lines before sending. Prices, schemes, stock and credit below are calculated by the server.</p>
    </section>
  )
}

function CorrectionForm({ order, item, onDone, onCancel }: { order: Order; item: OrderItem; onDone: () => void; onCancel: () => void }) {
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
      const body: { new_product_id?: string; new_quantity?: number; reason?: string } = { reason: reason.trim() }
      if (productId !== item.product_id) body.new_product_id = productId
      if (Number(quantity) !== Number(item.paid_quantity)) body.new_quantity = Number(quantity)
      await correctOrderItem(token, order.id, item.id, body)
      onDone()
    } catch (err) {
      setError(toMessage(err))
      setBusy(false)
    }
  }

  const products = catalogue.state.status === 'ready' ? catalogue.state.data.items : []
  const valid = /^\d+$/.test(quantity) && Number(quantity) > 0 && reason.trim().length > 0
    && (productId !== item.product_id || Number(quantity) !== Number(item.paid_quantity))
  return (
    <div className="mt-1 w-full space-y-3 rounded-xl bg-gray-50 p-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="block text-xs font-bold text-ink-soft">
          Product
          <select value={productId} onChange={(e) => setProductId(e.target.value)} className="mt-1 block min-h-11 w-full rounded-lg border border-gray-300 bg-white px-2 text-sm text-ink">
            {products.length === 0 && <option value={item.product_id}>{item.product_name}</option>}
            {products.map((p) => <option key={p.id} value={p.id}>{`${p.name} (${p.sku}) · ${qty(p.stock_cases)} in stock`}</option>)}
          </select>
        </label>
        <label className="block text-xs font-bold text-ink-soft">
          {item.order_unit === 'case' ? 'Cases' : 'Quantity'}
          <input inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value.replace(/\D/g, '').slice(0, 5))} className="mt-1 block min-h-11 w-24 rounded-lg border border-gray-300 bg-white px-2 text-sm text-ink" />
        </label>
      </div>
      <label className="block text-xs font-bold text-ink-soft">
        Reason (required, kept in the order history)
        <input value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Retailer phoned to change quantity" className="mt-1 block min-h-11 w-full rounded-lg border border-gray-300 bg-white px-2 text-sm text-ink" />
      </label>
      {error && <ErrorBox message={error} />}
      <div className="flex gap-2">
        <Button busy={busy} disabled={!valid} onClick={save}>Save correction</Button>
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
      <p className="text-xs text-ink-soft">Re-priced with the prices and schemes that applied when the order was placed. For AI orders, a product change also teaches the AI what this retailer’s words mean.</p>
    </div>
  )
}

/** Accept or Reject in one click (reject stores a default reason), or ask the retailer /
 *  salesman a question. If the server finds a problem on Accept (over the credit limit, or
 *  prices / schemes changed since the order was placed) it is shown with "Accept anyway". */
type Decided = 'accepted' | 'rejected' | 'clarification'

function Decision({ review, onDone }: { review: OrderReview; onDone: (what: Decided) => void }) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const o = review.order
  const [busy, setBusy] = useState<'accept' | 'reject' | 'clarify' | null>(null)
  const [asking, setAsking] = useState(false)
  const [question, setQuestion] = useState('')
  const [problem, setProblem] = useState<{ code: string; message: string } | null>(null)
  const [error, setError] = useState('')

  async function accept(anyway = false) {
    setBusy('accept')
    setError('')
    try {
      const overCredit = anyway && problem?.code === 'CREDIT_LIMIT_EXCEEDED'
      const changed = anyway && problem?.code === 'ORDER_DATA_CHANGED'
      await approveOrder(token, o.id, overCredit ? 'Accepted above the credit limit by the order desk' : undefined, changed)
      onDone('accepted')
    } catch (err) {
      if (err instanceof ApiError && (err.code === 'CREDIT_LIMIT_EXCEEDED' || err.code === 'ORDER_DATA_CHANGED')) {
        setProblem({ code: err.code, message: err.message })
      } else {
        setProblem(null)
        setError(toMessage(err))
      }
      setBusy(null)
    }
  }

  async function clarify() {
    setBusy('clarify')
    setError('')
    try {
      await requestClarification(token, o.id, question.trim())
      onDone('clarification')
    } catch (err) {
      setError(toMessage(err))
      setBusy(null)
    }
  }

  async function reject() {
    setBusy('reject')
    setError('')
    try {
      await rejectOrder(token, o.id)
      onDone('rejected')
    } catch (err) {
      setError(toMessage(err))
      setBusy(null)
    }
  }

  return (
    <section className="rounded-2xl border-2 border-leaf-200 bg-leaf-50/30 p-4">
      <h2 className="font-extrabold text-ink">Your decision</h2>
      <p className="mt-0.5 text-xs text-ink-soft">Choose one. The retailer and salesman see the result.</p>
      <div className="mt-3 space-y-3">
        <div>
          <Button className="w-full" busy={busy === 'accept'} disabled={busy !== null} onClick={() => accept()}>✓ Accept order</Button>
          <p className="mt-1 text-xs text-ink-soft">Everything looks right. Stock is deducted and the amount is added to the retailer’s balance.</p>
        </div>
        <div>
          <Button className="w-full" variant="danger" busy={busy === 'reject'} disabled={busy !== null} onClick={reject}>✕ Reject order</Button>
          <p className="mt-1 text-xs text-ink-soft">Cancel it. Nothing is deducted and the credit held by this order is released.</p>
        </div>
        <div>
          <Button variant="secondary" className="w-full" disabled={busy !== null} onClick={() => setAsking((v) => !v)}>
            ? {o.status === 'CLARIFICATION_REQUIRED' ? 'Ask again' : 'Ask the retailer a question'}
          </Button>
          <p className="mt-1 text-xs text-ink-soft">Something is unclear (product, quantity, price). The order waits until you decide.</p>
        </div>
      </div>
      {asking && (
        <div className="mt-3 space-y-2">
          <label className="block text-xs font-bold text-ink-soft">
            What needs to be clarified? (the retailer and salesman see this)
            <textarea rows={3} maxLength={1000} value={question} onChange={(e) => setQuestion(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-ink" />
          </label>
          <Button className="w-full" busy={busy === 'clarify'} disabled={busy !== null || !question.trim()} onClick={clarify}>Send clarification request</Button>
        </div>
      )}
      {problem && (
        <div className="mt-3 space-y-2">
          <Notice tone="warn">{problem.message}</Notice>
          <Button className="w-full" busy={busy === 'accept'} disabled={busy !== null} onClick={() => accept(true)}>
            {problem.code === 'CREDIT_LIMIT_EXCEEDED' ? 'Accept anyway (above credit limit)' : 'Accept anyway (at the order’s prices)'}
          </Button>
        </div>
      )}
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
    </section>
  )
}

/** Shown on an order that is waiting: what to do, in order. */
function NextSteps({ hasWarnings }: { hasWarnings: boolean }) {
  const steps = [
    hasWarnings ? 'Read the yellow “Check before deciding” box first.' : 'No problems were found automatically.',
    'Check the products, quantities and prices below. Use “Edit line” if something must change.',
    'Check stock and the retailer’s credit (shown with each line and in the Credit box).',
    'Then choose Accept or Reject in “Your decision”.',
  ]
  return (
    <section className="mt-4 rounded-2xl border border-leaf-200 bg-leaf-50 p-4" aria-label="What to do">
      <p className="font-extrabold text-leaf-900">This order is waiting for your decision</p>
      <ol className="mt-2 grid gap-1.5 text-sm text-ink sm:grid-cols-2">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-leaf-700 text-xs font-bold text-white">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** After a decision: what happened, and a one-click way to the next waiting order. */
function DecidedBanner({ what, orderId }: { what: Decided; orderId: string }) {
  const next = useLoad((t, s) => listDeskOrders(t, { view: 'incoming', sort: 'oldest', limit: 2 }, s), `next-after-${orderId}-${what}`)
  const nextId = next.state.status === 'ready' ? next.state.data.items.find((x) => x.id !== orderId)?.id : undefined
  const text = {
    accepted: 'Order accepted. Stock was deducted and the retailer can see it is confirmed.',
    rejected: 'Order rejected. The retailer can see it, and the held credit was released.',
    clarification: 'Question sent. The order is now under “Clarification” until you decide.',
  }[what]
  return (
    <section role="status" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-leaf-200 bg-leaf-50 p-4">
      <p className="font-bold text-leaf-900">✓ {text}</p>
      <div className="flex flex-wrap gap-2">
        {nextId && <Link to={`/desk/orders/${nextId}`} className="inline-flex min-h-11 items-center rounded-lg bg-leaf-700 px-4 text-sm font-bold text-white hover:bg-leaf-800">Next order to review →</Link>}
        <Link to="/desk/incoming" className="inline-flex min-h-11 items-center rounded-lg bg-white px-4 text-sm font-bold text-leaf-800 ring-1 ring-gray-300 hover:bg-gray-50">Back to incoming orders</Link>
      </div>
      {next.state.status === 'ready' && !nextId && <p className="w-full text-sm text-ink-soft">No other orders are waiting.</p>}
    </section>
  )
}
