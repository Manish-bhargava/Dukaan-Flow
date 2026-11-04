import { useState } from 'react'
import { fetchProduct, type Product } from '../../api/products'
import { useLoad } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { cartLineFor } from '../../cart/lines'
import { Link } from '../../components/Link'
import { ProductImage, StockNote } from '../../components/ProductParts'
import { Button, ErrorBox, Loading, Notice, QtyStepper } from '../../components/ui'
import { gstLabel, offerDetail, offerHeadline, plural, qty, rupees } from '../../format'

export function ProductDetailPage({ productId }: { productId: string }) {
  const product = useLoad((t, s) => fetchProduct(t, productId, s), productId)
  if (product.state.status === 'error') return <ErrorBox message={product.state.message} onRetry={product.reload} />
  if (product.state.status === 'loading') return <Loading label="Loading product…" />
  return <ProductDetail product={product.state.data} />
}

function ProductDetail({ product: p }: { product: Product }) {
  const { quantityOf, setQuantity } = useCart()
  const inCart = quantityOf(p.id)
  const stock = Number(p.stock_cases)
  const [quantity, setQty] = useState(inCart || 1)
  const [added, setAdded] = useState(false)

  const facts: [string, string][] = [
    ['Brand', p.brand],
    ['Category', p.category.name],
    ['Pack size', p.pack_size],
    ['SKU', p.sku],
    ['Case contains', `${qty(p.units_per_case)} ${p.base_unit}s`],
    ['Ordered in', `${p.order_unit}s`],
    ['GST', `${qty(p.gst_rate)}% (${p.price.tax_inclusive ? 'included in price' : 'added to price'})`],
  ]

  return (
    <>
      <Link to="/home" className="text-sm font-bold text-leaf-700">← Back to catalogue</Link>
      <div className="mt-4 grid gap-6 md:grid-cols-2 md:gap-10">
        <div className="mx-auto aspect-square w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6">
          <ProductImage product={p} large />
        </div>

        <div>
          <p className="text-xs font-bold uppercase tracking-wide text-leaf-600">{p.brand}</p>
          <h1 className="mt-1 text-2xl font-extrabold leading-tight text-ink">{p.name}</h1>
          <p className="text-sm text-ink-soft">
            {p.pack_size} · {p.sku}
          </p>

          <p className="mt-4">
            <span className="text-3xl font-extrabold text-ink">{rupees(p.price.case_price)}</span>
            <span className="text-base text-ink-soft"> / {p.order_unit}</span>
          </p>
          <p className="text-sm text-ink-soft">
            {gstLabel(p.gst_rate, p.price.tax_inclusive)}
            {p.price.price_basis === 'PIECE' && ` · ${rupees(p.price.dealer_price)} per ${p.base_unit}`}
          </p>
          <div className="mt-2">
            <StockNote product={p} />
          </div>

          {p.schemes.length > 0 && (
            <div className="mt-4 space-y-2">
              {p.schemes.map((s) => (
                <div key={s.id} className="rounded-xl border border-mango-200 bg-mango-100/60 px-4 py-3">
                  <p className="text-base font-extrabold text-leaf-900">{offerHeadline(s, p.order_unit)}</p>
                  <p className="mt-0.5 text-sm text-ink">{offerDetail(s, p.order_unit)}</p>
                </div>
              ))}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <QtyStepper label={p.name} value={quantity} max={stock} onChange={(n) => { setQty(Math.max(1, n)); setAdded(false) }} />
            <Button
              disabled={!p.in_stock}
              onClick={() => {
                setQuantity(cartLineFor(p), quantity)
                setAdded(true)
              }}
              className="min-w-40"
            >
              {!p.in_stock ? 'Out of stock' : inCart ? 'Update cart' : 'Add to cart'}
            </Button>
          </div>
          {added && (
            <div className="mt-3">
              <Notice tone="success">
                {plural(quantity, p.order_unit)} in your cart. <Link to="/cart" className="font-bold underline">View cart</Link> to see the scheme and total.
              </Notice>
            </div>
          )}
          {!added && inCart > 0 && (
            <p className="mt-2 text-sm text-ink-soft">
              {plural(inCart, p.order_unit)} already in your cart. <Link to="/cart" className="font-bold text-leaf-700 underline">View cart</Link>
            </p>
          )}

          <dl className="mt-6 divide-y divide-gray-100 border-y border-gray-100 text-sm">
            {facts.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 py-2">
                <dt className="text-ink-soft">{label}</dt>
                <dd className="text-right font-semibold text-ink">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </>
  )
}
