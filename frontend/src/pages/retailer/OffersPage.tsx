import { fetchProducts } from '../../api/products'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { ProductCard } from '../../components/ProductParts'
import { Empty, ErrorBox, Loading } from '../../components/ui'
import { offerDetail, offerHeadline } from '../../format'

const MAX_OFFERS = 100

/** Products with a scheme active now, at this retailer's prices (GET /products?has_scheme=true). */
export function OffersPage() {
  const offers = useLoad((t, s) => fetchProducts(t, { has_scheme: true, limit: MAX_OFFERS }, s), 'offers')

  return (
    <>
      <h1 className="text-xl font-extrabold text-ink">Offers & Schemes</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Current schemes on products at your prices. Free cases and discounts are applied automatically when you order the qualifying quantity.
      </p>

      <div className="mt-4">
        {offers.state.status === 'error' ? (
          <ErrorBox message={offers.state.message} onRetry={offers.reload} />
        ) : offers.state.status === 'loading' ? (
          <Loading label="Loading offers…" />
        ) : offers.state.data.items.length === 0 ? (
          <Empty title="No offers right now">
            Check back later, or browse the <Link to="/home" className="font-bold text-leaf-700 underline">full catalogue</Link>.
          </Empty>
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 sm:gap-4">
            {offers.state.data.items.map((p) => (
              <ProductCard key={p.id} product={p}>
                {p.schemes.map((s) => (
                  <div key={s.id} className="mt-2 rounded-lg border border-leaf-100 bg-leaf-50 px-2.5 py-2">
                    <p className="text-sm font-extrabold text-leaf-800">{offerHeadline(s, p.order_unit)}</p>
                    <p className="mt-0.5 text-xs text-ink">{offerDetail(s, p.order_unit)}</p>
                  </div>
                ))}
              </ProductCard>
            ))}
          </ul>
        )}
        {offers.state.status === 'ready' && offers.state.data.total > MAX_OFFERS && (
          <p className="mt-3 text-sm text-ink-soft">Showing the first {MAX_OFFERS} of {offers.state.data.total} offers.</p>
        )}
      </div>
    </>
  )
}
