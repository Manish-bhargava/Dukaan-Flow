import { useEffect, useState } from 'react'
import type { AuthUser } from '../api/auth'
import { ApiError } from '../api/client'
import { fetchCategories, fetchProducts, type Category, type Product, type Scheme } from '../api/products'
import { SESSION_EXPIRED, useAuth } from '../auth/AuthContext'
import { ProductArt } from '../components/ProductArt'
import { artForCategory } from '../components/productKinds'
import { Spinner } from '../components/Spinner'

const PAGE_SIZE = 12
const LOW_STOCK_CASES = 10
const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const num = (value: string) => Number(value).toLocaleString('en-IN')

type Load = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready' }

export function RetailerHome({ user, token }: { user: AuthUser; token: string }) {
  const { signOut } = useAuth()
  const [categories, setCategories] = useState<Category[]>([])
  const [categoryId, setCategoryId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [load, setLoad] = useState<Load>({ status: 'loading' })
  const [retry, setRetry] = useState(0)
  const [orderList, setOrderList] = useState<Record<string, number>>({}) // product id -> cases

  // An expired or revoked token ends the session; other errors are shown in place.
  const handleError = (err: unknown) => {
    if (err instanceof DOMException && err.name === 'AbortError') return
    if (err instanceof ApiError && (err.status === 401 || err.code === 'ACCOUNT_DISABLED')) {
      signOut(err.status === 401 ? SESSION_EXPIRED : err.message)
      return
    }
    setLoad({ status: 'error', message: err instanceof Error ? err.message : 'Could not load products.' })
  }

  useEffect(() => {
    const controller = new AbortController()
    fetchCategories(token, controller.signal)
      .then((res) => setCategories(res.data))
      .catch(handleError)
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // Debounce typing in the search box; a new search or category starts again from page 1.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const chooseCategory = (id: string) => {
    setCategoryId(id)
    setPage(1)
  }

  useEffect(() => {
    const controller = new AbortController()
    setLoad({ status: 'loading' })
    fetchProducts(token, { search, category_id: categoryId, page, limit: PAGE_SIZE }, controller.signal)
      .then((res) => {
        setProducts((prev) => (page === 1 ? res.data.items : [...prev, ...res.data.items]))
        setTotal(res.data.total)
        setLoad({ status: 'ready' })
      })
      .catch(handleError)
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, search, categoryId, page, retry])

  const setCases = (id: string, cases: number) =>
    setOrderList((list) => {
      const next = { ...list }
      if (cases > 0) next[id] = cases
      else delete next[id]
      return next
    })

  const selectedLines = Object.keys(orderList).length
  const selectedCases = Object.values(orderList).reduce((sum, n) => sum + n, 0)
  const firstLoad = load.status === 'loading' && page === 1

  return (
    <main className={`mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-10 ${selectedLines ? 'pb-32' : ''}`}>
      <Welcome name={user.name} />

      <section id="catalogue" className="mt-10 scroll-mt-20">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-2xl font-extrabold tracking-tight text-leaf-900">Catalogue</h2>
            <p className="mt-1 text-sm text-ink-soft">Your dealer prices per case, before GST. Schemes apply automatically when you order.</p>
          </div>
          <label className="relative block w-full sm:w-80">
            <span className="sr-only">Search products</span>
            <svg viewBox="0 0 24 24" className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-soft" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.35-4.35" />
            </svg>
            <input
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search products, brands, SKU"
              maxLength={100}
              className="w-full rounded-full border-0 bg-white py-3 pl-12 pr-4 text-sm ring-1 ring-cream-300 outline-none transition focus:ring-2 focus:ring-leaf-500"
            />
          </label>
        </div>

        <div className="-mx-4 mt-5 flex gap-2 overflow-x-auto px-4 pb-2 sm:mx-0 sm:flex-wrap sm:px-0" role="tablist" aria-label="Categories">
          <CategoryChip active={categoryId === ''} onClick={() => chooseCategory('')} label="All" />
          {categories.map((c) => (
            <CategoryChip key={c.id} active={categoryId === c.id} onClick={() => chooseCategory(c.id)} label={c.name} kind={c.name} />
          ))}
        </div>

        {load.status === 'error' ? (
          <div className="mt-8 rounded-3xl bg-red-50 p-8 text-center ring-1 ring-red-200">
            <p className="font-semibold text-red-800">{load.message}</p>
            <button
              type="button"
              onClick={() => setRetry((n) => n + 1)}
              className="mt-4 rounded-full bg-leaf-700 px-6 py-2.5 text-sm font-bold text-cream-50 hover:bg-leaf-800"
            >
              Try again
            </button>
          </div>
        ) : firstLoad ? (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-80 animate-pulse rounded-3xl bg-cream-100" />
            ))}
          </div>
        ) : products.length === 0 ? (
          <div className="mt-8 rounded-3xl bg-white p-10 text-center ring-1 ring-cream-200">
            <ProductArt kind="carton" className="mx-auto h-24 w-24" />
            <p className="mt-3 font-bold text-leaf-900">No products found</p>
            <p className="mt-1 text-sm text-ink-soft">
              {search || categoryId ? 'Try another search or category.' : 'No products are priced for your shop yet. Please contact your distributor.'}
            </p>
          </div>
        ) : (
          <>
            <p className="mt-4 text-sm font-semibold text-ink-soft">
              Showing {products.length} of {total} products
            </p>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {products.map((p) => (
                <ProductCard key={p.id} product={p} cases={orderList[p.id] ?? 0} onChange={(n) => setCases(p.id, n)} />
              ))}
            </div>
            {products.length < total && (
              <div className="mt-8 text-center">
                <button
                  type="button"
                  disabled={load.status === 'loading'}
                  onClick={() => setPage((n) => n + 1)}
                  className="inline-flex items-center gap-2 rounded-full bg-white px-7 py-3 font-bold text-leaf-700 ring-1 ring-leaf-200 transition hover:bg-leaf-50 disabled:opacity-60"
                >
                  {load.status === 'loading' && <Spinner className="h-4 w-4" />} Load more
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {selectedLines > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-leaf-900 bg-leaf-800 px-4 py-4 text-cream-50 shadow-2xl sm:px-8">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-bold">
                {selectedLines} product{selectedLines > 1 ? 's' : ''} · {selectedCases} case{selectedCases > 1 ? 's' : ''} in your order list
              </p>
              <p className="text-xs text-leaf-100">Final prices, schemes and GST are calculated by DukaanFlow when the order is placed.</p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setOrderList({})} className="rounded-full px-4 py-2.5 text-sm font-bold text-leaf-100 hover:bg-leaf-700">
                Clear
              </button>
              <button
                type="button"
                disabled
                title="Order placement is the next milestone"
                className="cursor-not-allowed rounded-full bg-mango-400/60 px-5 py-2.5 text-sm font-bold text-leaf-950"
              >
                Place order · coming soon
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

function Welcome({ name }: { name: string }) {
  const actions = [
    { title: 'Browse catalogue', text: 'Your prices & schemes', href: '#catalogue', ready: true },
    { title: 'Order by message', text: 'Type it in Hindi or English', ready: false },
    { title: 'My orders', text: 'Track status & history', ready: false },
    { title: 'Credit', text: 'Limit & outstanding', ready: false },
  ]
  return (
    <section className="animate-fade-up relative overflow-hidden rounded-[2rem] bg-leaf-800 p-6 text-cream-50 sm:p-10">
      <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-mango-400/20 blur-3xl" />
      <div className="relative flex items-start justify-between gap-6">
        <div>
          <p className="text-sm font-bold uppercase tracking-wider text-mango-300">Retailer</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">Namaste, {name.split(' ')[0]}!</h1>
          <p className="mt-2 max-w-lg text-leaf-100">What does your shop need today?</p>
        </div>
        <div className="hidden gap-3 md:flex" aria-hidden="true">
          {(['biscuits', 'tea', 'noodles'] as const).map((kind, i) => (
            <div key={kind} className="animate-float rounded-2xl bg-cream-100 p-2" style={{ animationDelay: `${i * 0.5}s` }}>
              <ProductArt kind={kind} className="h-16 w-16" />
            </div>
          ))}
        </div>
      </div>
      <div className="relative mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {actions.map((a) => {
          const body = (
            <>
              <span className="flex items-center justify-between gap-2">
                <span className="font-bold">{a.title}</span>
                {!a.ready && <span className="rounded-full bg-cream-50/15 px-2 py-0.5 text-[10px] font-bold uppercase">Soon</span>}
              </span>
              <span className="mt-1 block text-xs text-leaf-100">{a.text}</span>
            </>
          )
          return a.ready ? (
            <a key={a.title} href={a.href} className="rounded-2xl bg-mango-400 p-4 text-leaf-950 transition hover:-translate-y-0.5 hover:bg-mango-300 [&_span.text-leaf-100]:text-leaf-900/70">
              {body}
            </a>
          ) : (
            <div key={a.title} className="rounded-2xl bg-leaf-700/70 p-4 ring-1 ring-leaf-600/60" aria-disabled="true">
              {body}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function CategoryChip({ active, onClick, label, kind }: { active: boolean; onClick: () => void; label: string; kind?: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex shrink-0 items-center gap-2 rounded-full py-1.5 pl-2 pr-4 text-sm font-bold ring-1 transition ${
        active ? 'bg-leaf-700 text-cream-50 ring-leaf-700' : 'bg-white text-ink-soft ring-cream-300 hover:ring-leaf-300'
      } ${kind ? '' : 'pl-4'}`}
    >
      {kind && <ProductArt kind={artForCategory(kind)} className="h-7 w-7" />}
      {label}
    </button>
  )
}

function schemeText(s: Scheme): string {
  const min = Number(s.min_quantity)
  return s.scheme_type === 'FREE_GOODS'
    ? `Buy ${min} get ${Number(s.free_quantity)} free`
    : `${Number(s.discount_percentage)}% off on ${min}+ cases`
}

function ProductCard({ product: p, cases, onChange }: { product: Product; cases: number; onChange: (cases: number) => void }) {
  const stock = Number(p.stock_cases)
  const low = p.in_stock && stock <= LOW_STOCK_CASES
  return (
    <article className="group flex flex-col rounded-3xl bg-white p-4 ring-1 ring-cream-200 transition duration-300 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-leaf-900/5">
      <div className="relative flex h-36 items-center justify-center rounded-2xl bg-cream-100">
        <ProductArt kind={artForCategory(p.category.name)} label={p.pack_size} className="h-28 w-28 transition-transform duration-300 group-hover:scale-105" />
        {p.schemes.map((s) => (
          <span key={s.id} className="absolute left-3 top-3 rounded-full bg-mango-400 px-2.5 py-1 text-[11px] font-extrabold text-leaf-950 shadow-sm">
            {schemeText(s)}
          </span>
        ))}
      </div>
      <p className="mt-4 text-xs font-bold uppercase tracking-wider text-leaf-600">{p.brand}</p>
      <h3 className="mt-1 font-bold leading-snug text-leaf-900">
        {p.name}
        {!p.name.toLowerCase().endsWith(p.pack_size.toLowerCase()) && <span className="font-semibold text-ink-soft"> {p.pack_size}</span>}
      </h3>
      <p className="mt-1 text-xs text-ink-soft">
        {num(p.units_per_case)} {p.base_unit}s per {p.order_unit} · {p.sku}
      </p>

      <div className="mt-3 flex items-end justify-between gap-2">
        <div>
          <p className="text-xl font-extrabold text-leaf-900">
            {rupees.format(Number(p.price.case_price))}
            <span className="text-sm font-semibold text-ink-soft"> / {p.order_unit}</span>
          </p>
          <p className="text-xs text-ink-soft">
            {p.price.tax_inclusive ? `incl. ${Number(p.gst_rate)}% GST` : `+ ${Number(p.gst_rate)}% GST`}
            {p.price.price_basis === 'PIECE' && ` · ${rupees.format(Number(p.price.dealer_price))} / ${p.base_unit}`}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
            !p.in_stock ? 'bg-red-50 text-red-700' : low ? 'bg-mango-100 text-mango-600' : 'bg-leaf-50 text-leaf-700'
          }`}
        >
          {!p.in_stock ? 'Out of stock' : low ? `Only ${num(p.stock_cases)} left` : 'In stock'}
        </span>
      </div>

      <div className="mt-auto pt-4">
        {cases === 0 ? (
          <button
            type="button"
            disabled={!p.in_stock}
            onClick={() => onChange(1)}
            className="w-full rounded-full bg-leaf-700 py-2.5 text-sm font-bold text-cream-50 transition hover:bg-leaf-800 disabled:cursor-not-allowed disabled:bg-cream-200 disabled:text-ink-soft"
          >
            {p.in_stock ? 'Add to order list' : 'Unavailable'}
          </button>
        ) : (
          <div className="flex items-center justify-between rounded-full bg-leaf-50 p-1 ring-1 ring-leaf-200">
            <StepButton label="Remove one case" onClick={() => onChange(cases - 1)}>−</StepButton>
            <span className="text-sm font-extrabold text-leaf-900">
              {cases} {p.order_unit}
              {cases > 1 ? 's' : ''}
            </span>
            <StepButton label="Add one case" onClick={() => onChange(cases + 1)} disabled={cases >= stock}>+</StepButton>
          </div>
        )}
      </div>
    </article>
  )
}

function StepButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-lg font-bold text-leaf-700 shadow-sm transition hover:bg-leaf-700 hover:text-cream-50 disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-leaf-700"
    >
      {children}
    </button>
  )
}
