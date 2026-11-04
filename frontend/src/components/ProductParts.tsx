import { useState, type ReactNode } from 'react'
import type { Product } from '../api/products'
import { useCart } from '../cart/CartContext'
import { cartLineFor } from '../cart/lines'
import { gstLabel, offerHeadline, plural, rupees } from '../format'
import { Link } from './Link'
import { PackShot } from './PackShot'
import { Button, QtyStepper } from './ui'

const LOW_STOCK_CASES = 10

/**
 * Product photo from the API (Cloudinary, already optimized), or a pack illustration when
 * there is none or it fails to load. Always shown whole (object-contain), never cropped.
 */
export function ProductImage({ product: p, large = false, className = 'h-full w-full' }: { product: Product; large?: boolean; className?: string }) {
  const [failed, setFailed] = useState(false)
  const src = large ? p.image_url : (p.thumbnail_url ?? p.image_url)
  if (src && !failed) {
    return (
      <img
        src={src}
        alt={p.name}
        loading={large ? 'eager' : 'lazy'}
        decoding="async"
        onError={() => setFailed(true)}
        className={`${className} object-contain`}
      />
    )
  }
  return <PackShot name={p.name} brand={p.brand} category={p.category.name} packSize={p.pack_size} className={className} />
}

export function StockNote({ product: p }: { product: Product }) {
  const stock = Number(p.stock_cases)
  const low = p.in_stock && stock <= LOW_STOCK_CASES
  return (
    <span className={`text-xs font-bold ${!p.in_stock ? 'text-red-700' : low ? 'text-mango-600' : 'text-leaf-700'}`}>
      {!p.in_stock ? 'Out of stock' : low ? `Only ${plural(stock, p.order_unit)} left` : `${plural(stock, p.order_unit)} in stock`}
    </span>
  )
}

/** "Add" button, then a +/- stepper once the product is in the cart (cases, up to stock). */
export function AddToCart({ product: p, wide = false }: { product: Product; wide?: boolean }) {
  const { quantityOf, setQuantity } = useCart()
  const inCart = quantityOf(p.id)
  return inCart > 0 ? (
    <QtyStepper label={p.name} value={inCart} max={Number(p.stock_cases)} onChange={(n) => setQuantity(cartLineFor(p), n)} />
  ) : (
    <Button disabled={!p.in_stock} onClick={() => setQuantity(cartLineFor(p), 1)} className={wide ? 'w-full' : 'w-24'}>
      {p.in_stock ? 'Add' : 'Out of stock'}
    </Button>
  )
}

export function SchemeBadges({ product: p }: { product: Product }) {
  if (p.schemes.length === 0) return null
  return (
    <div className="flex flex-col items-start gap-1">
      {p.schemes.map((s) => (
        <span key={s.id} className="rounded-md bg-mango-300 px-2 py-1 text-xs font-extrabold text-leaf-950 shadow-sm">
          {offerHeadline(s, p.order_unit)}
        </span>
      ))}
    </div>
  )
}

/** Catalogue card: large image, key facts, active schemes, Add and View details. */
export function ProductCard({ product: p, children }: { product: Product; children?: ReactNode }) {
  const details = `/products/${p.id}`
  return (
    <li className="flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white">
      <Link to={details} className="relative block aspect-square bg-white p-3" aria-label={`${p.name}: view details`}>
        <ProductImage product={p} />
        <div className="absolute left-2 top-2">
          <SchemeBadges product={p} />
        </div>
      </Link>
      <div className="flex flex-1 flex-col border-t border-gray-100 p-3">
        <p className="text-[11px] font-bold uppercase tracking-wide text-leaf-600">{p.brand}</p>
        <Link to={details} className="font-bold leading-snug text-ink hover:text-leaf-700">
          {p.name}
        </Link>
        <p className="text-xs text-ink-soft">
          {p.pack_size} · {p.sku}
        </p>
        <p className="mt-2">
          <span className="text-lg font-extrabold text-ink">{rupees(p.price.case_price)}</span>
          <span className="text-xs text-ink-soft"> / {p.order_unit}</span>
        </p>
        <p className="text-xs text-ink-soft">{gstLabel(p.gst_rate, p.price.tax_inclusive)}</p>
        <div className="mt-1">
          <StockNote product={p} />
        </div>
        {children}
        <div className="mt-auto flex flex-col items-stretch gap-1 pt-3">
          <div className="flex justify-center">
            <AddToCart product={p} wide />
          </div>
          <Link to={details} className="inline-flex min-h-11 items-center justify-center text-sm font-bold text-leaf-700 hover:underline">
            View details
          </Link>
        </div>
      </div>
    </li>
  )
}
