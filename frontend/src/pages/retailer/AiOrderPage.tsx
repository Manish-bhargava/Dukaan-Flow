import { useState } from 'react'
import { extractOrder, type Extraction, type ExtractionItem } from '../../api/aiOrders'
import { fetchProducts, type Product } from '../../api/products'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { cartLineFor } from '../../cart/lines'
import { Button, ErrorBox, Notice } from '../../components/ui'
import { qty } from '../../format'
import { navigate } from '../../router'

const EXAMPLE = 'bhaiya 5 peti biscuit chhota, 2 peti washing powder 1 kilo, chai patti 250 wala 1 peti'

interface DraftRow {
  key: string
  itemId: string | null
  originalText: string | null
  suggestions: string[] // product ids suggested by the AI, best first
  productId: string
  quantity: string
  unit: string
  note: string | null
}

function toRow(item: ExtractionItem): DraftRow {
  const order_unit = item.product?.order_unit
  return {
    key: item.id,
    itemId: item.id,
    originalText: item.original_text,
    suggestions: [item.product?.product_id, ...item.alternatives.map((a) => a.product_id)].filter((id): id is string => !!id),
    productId: item.product?.product_id ?? '',
    quantity: item.quantity ? String(Number(item.quantity)) : '',
    unit: item.unit && item.unit === order_unit ? item.unit : '',
    note: item.clarification,
  }
}

export function AiOrderPage() {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [rows, setRows] = useState<DraftRow[]>([])

  async function read() {
    if (!message.trim()) return
    setBusy(true)
    setError('')
    try {
      const result = (await extractOrder(token, message.trim())).data
      setExtraction(result)
      setRows(result.items.map(toRow))
      if (result.items.length === 0) setError('No products were found in the message. Try writing the product and quantity, e.g. "5 peti biscuit".')
    } catch (err) {
      setError(toMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1 className="text-xl font-extrabold text-ink">Order by message</h1>
      <p className="mt-1 text-sm text-ink-soft">Paste or type your order as you would send it on WhatsApp, in Hindi, Hinglish or English. Nothing is ordered until you review it.</p>

      {!extraction || rows.length === 0 ? (
        <div className="mt-4 max-w-2xl">
          <label htmlFor="message" className="sr-only">Order message</label>
          <textarea
            id="message"
            rows={5}
            maxLength={2000}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={EXAMPLE}
            className="w-full rounded-lg border border-gray-300 p-3 text-base outline-none focus:border-leaf-600"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <Button busy={busy} disabled={!message.trim()} onClick={read}>
              {busy ? 'Reading your order…' : 'Read my order'}
            </Button>
            {!message && (
              <Button variant="secondary" onClick={() => setMessage(EXAMPLE)}>
                Use example
              </Button>
            )}
          </div>
          {error && (
            <div className="mt-3">
              <ErrorBox message={error} />
            </div>
          )}
        </div>
      ) : (
        <DraftReview
          extraction={extraction}
          rows={rows}
          setRows={setRows}
          onStartOver={() => {
            setExtraction(null)
            setRows([])
            setError('')
          }}
        />
      )}
    </>
  )
}

function DraftReview({
  extraction,
  rows,
  setRows,
  onStartOver,
}: {
  extraction: Extraction
  rows: DraftRow[]
  setRows: (update: (rows: DraftRow[]) => DraftRow[]) => void
  onStartOver: () => void
}) {
  const { addLines } = useCart()
  const catalogue = useLoad((t, s) => fetchProducts(t, { limit: 100 }, s), 'ai-catalogue')
  const products = new Map<string, Product>(catalogue.state.status === 'ready' ? catalogue.state.data.items.map((p) => [p.id, p]) : [])
  const [error, setError] = useState('')

  const update = (key: string, patch: Partial<DraftRow>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const problem = (r: DraftRow): string | null => {
    const p = products.get(r.productId)
    if (!p) return 'Choose the product.'
    if (!/^\d+$/.test(r.quantity) || Number(r.quantity) <= 0) return 'Enter the number of cases.'
    if (r.unit !== p.order_unit) return `Confirm the unit (${p.order_unit}s).`
    return null
  }
  const unresolved = rows.filter((r) => problem(r) !== null).length

  function addToCart() {
    const ids = rows.map((r) => r.productId)
    if (new Set(ids).size !== ids.length) {
      setError('The same product appears twice. Remove one line or combine the quantities.')
      return
    }
    const itemByProduct: Record<string, string> = {}
    for (const r of rows) if (r.itemId) itemByProduct[r.productId] = r.itemId
    addLines(
      rows.map((r) => ({ ...cartLineFor(products.get(r.productId)!), quantity: Number(r.quantity) })),
      { extractionId: extraction.extraction_id, itemByProduct },
    )
    navigate('/cart')
  }

  return (
    <div className="mt-4">
      <Notice>
        <span className="font-bold">Your message:</span> “{extraction.original_message}”
      </Notice>
      {catalogue.state.status === 'error' && (
        <div className="mt-3">
          <ErrorBox message={catalogue.state.message} onRetry={catalogue.reload} />
        </div>
      )}

      <ul className="mt-4 divide-y divide-gray-200 border-y border-gray-200">
        {rows.map((r) => {
          const p = products.get(r.productId)
          const issue = problem(r)
          const others = [...products.values()].filter((x) => !r.suggestions.includes(x.id))
          return (
            <li key={r.key} className="py-4">
              {r.originalText && <p className="text-sm text-ink-soft">From: “{r.originalText}”</p>}
              <div className="mt-2 grid gap-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
                <label className="block">
                  <span className="text-xs font-bold text-ink-soft">Product</span>
                  <select
                    value={r.productId}
                    onChange={(e) => update(r.key, { productId: e.target.value })}
                    className="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-2 text-base"
                  >
                    <option value="">Choose a product…</option>
                    {r.suggestions.length > 0 && (
                      <optgroup label="Suggested">
                        {r.suggestions.map((id) => {
                          const s = products.get(id)
                          return s ? <option key={id} value={id}>{`${s.name} (${s.sku})`}</option> : null
                        })}
                      </optgroup>
                    )}
                    <optgroup label="All products">
                      {others.map((x) => (
                        <option key={x.id} value={x.id}>{`${x.name} (${x.sku})`}</option>
                      ))}
                    </optgroup>
                  </select>
                </label>
                <label className="block">
                  <span className="text-xs font-bold text-ink-soft">Quantity</span>
                  <input
                    inputMode="numeric"
                    value={r.quantity}
                    onChange={(e) => update(r.key, { quantity: e.target.value.replace(/\D/g, '').slice(0, 5) })}
                    className="mt-1 block min-h-11 w-24 rounded-lg border border-gray-300 px-2 text-base"
                  />
                </label>
                <label className="block">
                  <span className="text-xs font-bold text-ink-soft">Unit</span>
                  <select
                    value={r.unit}
                    onChange={(e) => update(r.key, { unit: e.target.value })}
                    className="mt-1 block min-h-11 w-32 rounded-lg border border-gray-300 bg-white px-2 text-base"
                  >
                    <option value="">Choose…</option>
                    {p && <option value={p.order_unit}>{p.order_unit}s</option>}
                  </select>
                </label>
                <button type="button" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} className="min-h-11 px-2 text-sm font-bold text-ink-soft hover:text-red-700">
                  Remove
                </button>
              </div>
              {p && !p.in_stock && <p className="mt-2 text-sm font-bold text-red-700">Out of stock at the moment.</p>}
              {p && p.in_stock && <p className="mt-2 text-xs text-ink-soft">{qty(p.stock_cases)} {p.order_unit}s in stock · {p.pack_size}</p>}
              {issue && r.note && <p className="mt-2 text-sm font-semibold text-mango-600">{r.note}</p>}
              {issue && !r.note && <p className="mt-2 text-sm font-semibold text-mango-600">{issue}</p>}
            </li>
          )
        })}
      </ul>

      <div className="mt-3">
        <Button
          variant="secondary"
          onClick={() =>
            setRows((rs) => [...rs, { key: `new-${Date.now()}-${Math.random()}`, itemId: null, originalText: null, suggestions: [], productId: '', quantity: '1', unit: '', note: null }])
          }
        >
          + Add another product
        </Button>
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBox message={error} />
        </div>
      )}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button disabled={unresolved > 0 || rows.length === 0 || catalogue.state.status !== 'ready'} onClick={addToCart}>
          Add {rows.length} item{rows.length === 1 ? '' : 's'} to cart
        </Button>
        <Button variant="secondary" onClick={onStartOver}>
          Start over
        </Button>
        {unresolved > 0 && <p className="text-sm font-semibold text-mango-600">{unresolved} line{unresolved === 1 ? ' needs' : 's need'} your check.</p>}
      </div>
    </div>
  )
}
