import { useCallback, useEffect, useState } from 'react'
import { fetchCategories, fetchProducts, type Product } from '../../api/products'
import { getOrder, listOrders } from '../../api/orders'
import { useErrorMessage, useLoad, useToken } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { Link } from '../../components/Link'
import { ProductCard, ProductImage } from '../../components/ProductParts'
import { Button, Empty, ErrorBox, Loading } from '../../components/ui'
import { offerHeadline, plural, rupees } from '../../format'
import { navigate } from '../../router'

const PAGE_SIZE = 20

export function CataloguePage() {
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const categories = useLoad((t, s) => fetchCategories(t, s), 'categories')
  const products = useCatalogue(search, categoryId, page)
  const { items, total } = products

  const chooseCategory = (id: string) => {
    setCategoryId(id)
    setPage(1)
  }

  return (
    <>
      <RepeatLastOrder />
      <OffersStrip />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-extrabold text-ink">Products</h1>
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by name or SKU"
          aria-label="Search products"
          maxLength={100}
          className="min-h-11 w-full rounded-lg border border-gray-300 px-3 text-base outline-none focus:border-leaf-600 sm:w-80"
        />
      </div>

      <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" role="tablist" aria-label="Categories">
        {[{ id: '', name: 'All' }, ...(categories.state.status === 'ready' ? categories.state.data : [])].map((c) => (
          <button
            key={c.id}
            type="button"
            role="tab"
            aria-selected={categoryId === c.id}
            onClick={() => chooseCategory(c.id)}
            className={`min-h-10 shrink-0 rounded-full px-4 text-sm font-bold ${
              categoryId === c.id ? 'bg-leaf-700 text-white' : 'bg-gray-100 text-ink-soft hover:bg-gray-200'
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {products.error ? (
          <ErrorBox message={products.error} onRetry={products.reload} />
        ) : products.loading && items.length === 0 ? (
          <Loading label="Loading products…" />
        ) : items.length === 0 ? (
          <Empty title="No products found">{search || categoryId ? 'Try another search or category.' : 'No products are priced for your shop yet.'}</Empty>
        ) : (
          <>
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 sm:gap-4">
              {items.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </ul>
            {items.length < total && (
              <div className="mt-4 text-center">
                <Button variant="secondary" busy={items.length < Math.min(total, page * PAGE_SIZE)} onClick={() => setPage((n) => n + 1)}>
                  Load more ({total - items.length} more)
                </Button>
              </div>
            )}
          </>
        )}
      </div>
      <CartBar />
    </>
  )
}

/** Home-page teaser for the Offers & Schemes section (only shown when there are offers). */
function OffersStrip() {
  const offers = useLoad((t, s) => fetchProducts(t, { has_scheme: true, limit: 4 }, s), 'offers-strip')
  if (offers.state.status !== 'ready' || offers.state.data.total === 0) return null
  const { items, total } = offers.state.data
  return (
    <section aria-labelledby="offers-strip" className="mb-5 rounded-xl border border-mango-200 bg-mango-100/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="offers-strip" className="font-extrabold text-ink">
          Offers & Schemes <span className="font-semibold text-ink-soft">· {plural(total, 'product')}</span>
        </h2>
        <Link to="/offers" className="inline-flex min-h-11 items-center text-sm font-bold text-leaf-700 underline">
          See all offers
        </Link>
      </div>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((p) => (
          <li key={p.id} className="flex items-center gap-3">
            <span className="block h-12 w-12 shrink-0 rounded-lg bg-white">
              <ProductImage product={p} />
            </span>
            <p className="min-w-0 text-sm">
              <span className="font-bold text-ink">{p.name}</span>
              <span className="block font-bold text-mango-600">{p.schemes.map((s) => offerHeadline(s, p.order_unit)).join(' · ')}</span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Offers to re-add the items of the retailer's most recent order. */
function RepeatLastOrder() {
  const token = useToken()
  const toMessage = useErrorMessage()
  const { addLines } = useCart()
  const last = useLoad((t, s) => listOrders(t, { limit: 1 }, s), 'last-order')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (last.state.status !== 'ready' || last.state.data.items.length === 0) return null
  const summary = last.state.data.items[0]

  async function repeat() {
    setBusy(true)
    setError('')
    try {
      const order = (await getOrder(token, summary.id)).data
      addLines(order.items.map((i) => ({
        product_id: i.product_id, sku: i.sku, name: i.product_name, pack_size: i.pack_size,
        order_unit: i.order_unit, category: '', quantity: Number(i.paid_quantity),
      })))
      navigate('/cart')
    } catch (err) {
      setError(toMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 px-4 py-3">
      <p className="text-sm text-ink">
        Last order <Link to={`/orders/${summary.id}`} className="font-bold text-leaf-700 underline">{summary.order_number}</Link>
        {' '}· {plural(summary.item_count, 'item')} · {rupees(summary.grand_total)}
      </p>
      <Button variant="secondary" busy={busy} onClick={repeat}>Repeat this order</Button>
      {error && <p className="w-full text-sm text-red-700">{error}</p>}
    </div>
  )
}

function CartBar() {
  const { count, lines } = useCart()
  if (!count) return null
  const cases = lines.reduce((sum, l) => sum + l.quantity, 0)
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.05)]">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
        <p className="text-sm font-bold text-ink">
          {plural(count, 'product')} · {plural(cases, 'case')}
        </p>
        <Link to="/cart" className="inline-flex min-h-11 items-center rounded-lg bg-leaf-700 px-5 text-sm font-bold text-white hover:bg-leaf-800">
          View cart
        </Link>
      </div>
    </div>
  )
}

/** Catalogue pages for the current search/category; "Load more" appends the next page. */
function useCatalogue(search: string, categoryId: string, page: number) {
  const token = useToken()
  const toMessage = useErrorMessage()
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchProducts(token, { search, category_id: categoryId, page, limit: PAGE_SIZE }, controller.signal)
      .then((res) => {
        setItems((prev) => (page === 1 ? res.data.items : [...prev, ...res.data.items]))
        setTotal(res.data.total)
        setError('')
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(toMessage(err))
        setLoading(false)
      })
    return () => controller.abort()
  }, [token, search, categoryId, page, attempt, toMessage])

  const reload = useCallback(() => {
    setLoading(true)
    setAttempt((n) => n + 1)
  }, [])
  return { items, total, loading, error, reload }
}
