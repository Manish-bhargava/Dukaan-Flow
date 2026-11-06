import { useCallback, useState } from 'react'
import { admin, type Price, type PriceBasis } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox, Notice } from '../../components/ui'
import { dateTime, rupees } from '../../format'
import { Pager } from '../desk/deskUi'
import { AdminPage, Card, Checkbox, ConfirmDialog, DataTable, Field, FilterBar, Loaded, Modal, SearchBox, Select, TextInput } from './adminUi'
import { useAction } from './adminHooks'

/** Set a price from now on: the default (all retailers without their own price) or one
 *  retailer's own. The backend closes the old price, so history is kept and placed orders
 *  keep the price they were placed at. */
export function PriceDialog({ productId, productName, retailer, current, hasOwn = false, onClose, onSaved }: {
  productId: string; productName: string; retailer?: { id: string; shop_name: string }; current: Price | null
  hasOwn?: boolean; onClose: () => void; onSaved: () => void
}) {
  const token = useToken()
  const action = useAction()
  const [price, setPrice] = useState(current ? String(Number(current.dealer_price)) : '')
  const [basis, setBasis] = useState<PriceBasis>(current?.price_basis ?? 'PIECE')
  const [inclusive, setInclusive] = useState(current?.tax_inclusive ?? false)
  const [removing, setRemoving] = useState(false)
  const valid = /^\d+(\.\d{1,2})?$/.test(price)

  async function save() {
    if (await action.run(() => admin.setPrice(token, { product_id: productId, retailer_id: retailer?.id ?? null, dealer_price: price, price_basis: basis, tax_inclusive: inclusive }))) onSaved()
  }

  return (
    <Modal title={retailer ? `Price for ${retailer.shop_name}` : 'Default price'} onClose={onClose} footer={<>
      {retailer && hasOwn && <Button variant="danger" onClick={() => setRemoving(true)}>Use default price</Button>}
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>Save price</Button>
    </>}>
      <p className="text-sm font-semibold text-ink">{productName}</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Dealer price (₹)"><TextInput value={price} onChange={setPrice} inputMode="decimal" /></Field>
        <Select label="Price per" value={basis} onChange={(v) => setBasis(v as PriceBasis)} options={[['PIECE', 'Piece'], ['CASE', 'Case']]} />
      </div>
      <Checkbox checked={inclusive} onChange={setInclusive}>Price includes GST</Checkbox>
      <Notice>Applies to orders priced from now on. Orders already placed keep their price. {retailer ? 'Only this retailer gets this price.' : 'Retailers with their own price are not affected.'}</Notice>
      {action.error && <ErrorBox message={action.error} />}
      {removing && retailer && (
        <ConfirmDialog title="Remove this retailer's price?" confirmLabel="Remove" danger onClose={() => setRemoving(false)}
          message={`${retailer.shop_name} will get the default price for ${productName} from now on (if there is no default price, the product leaves their catalogue).`}
          onConfirm={async () => { await admin.removePrice(token, productId, retailer.id); onSaved() }} />
      )}
    </Modal>
  )
}

export function PriceHistory({ productId }: { productId: string }) {
  const product = useLoad((t, s) => admin.product(t, productId, s), `price-history-${productId}`)
  return (
    <Loaded state={product.state} reload={product.reload}>
      {(p) => (
        <DataTable rows={p.price_history} rowKey={(h) => h.id} empty="No prices yet" columns={[
          { header: 'For', cell: (h) => h.retailer ? <Link to={`/admin/retailers/${h.retailer.id}`} className="text-leaf-700">{h.retailer.shop_name}</Link> : <b>Default</b> },
          { header: 'Price', align: 'right', cell: (h) => `${rupees(h.dealer_price)} / ${h.price_basis.toLowerCase()}${h.tax_inclusive ? ' incl. GST' : ''}` },
          { header: 'From', cell: (h) => dateTime(h.effective_from) },
          { header: 'Until', cell: (h) => (h.effective_to ? dateTime(h.effective_to) : <span className="font-bold text-leaf-700">Current</span>) },
          { header: 'Set by', cell: (h) => h.by ?? 'Seed / import', wide: true },
        ]} />
      )}
    </Loaded>
  )
}

const LIMIT = 15

export function PricingPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<{ id: string; name: string; current: Price | null } | null>(null)
  const [editing, setEditing] = useState(false)
  const [version, setVersion] = useState(0)
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const products = useLoad((t, s) => admin.products(t, { search, page, limit: LIMIT, status: 'active' }, s), `pricing|${search}|${page}|${version}`)

  return (
    <AdminPage title="Pricing" subtitle="Default dealer prices and their history. Retailer-specific prices are set on each retailer's page (Prices & schemes).">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <FilterBar><SearchBox value={search} onChange={onSearch} placeholder="Search product, SKU or brand" /></FilterBar>
          <Loaded state={products.state} reload={products.reload}>
            {(d) => (
              <>
                <DataTable rows={d.items} rowKey={(p) => p.id} loading={products.loading}
                  onRow={(p) => setSelected({ id: p.id, name: p.name, current: p.default_price ?? null })} columns={[
                    { header: 'Product', cell: (p) => <><span className={`font-semibold ${selected?.id === p.id ? 'text-leaf-700' : 'text-ink'}`}>{p.name}</span><span className="block text-xs text-ink-soft">{p.sku}</span></> },
                    { header: 'Default price', align: 'right', cell: (p) => (p.default_price ? `${rupees(p.default_price.dealer_price)} / ${p.default_price.price_basis.toLowerCase()}` : <span className="text-mango-600">Not set</span>) },
                    { header: 'Retailer prices', align: 'right', cell: (p) => p.retailer_prices ?? 0 },
                  ]} />
                <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
              </>
            )}
          </Loaded>
        </div>
        <Card title={selected ? selected.name : 'Price history'} actions={selected && <Button onClick={() => setEditing(true)}>Set default price</Button>}>
          {selected ? <PriceHistory key={`${selected.id}-${version}`} productId={selected.id} /> : <p className="text-sm text-ink-soft">Choose a product to see its prices over time.</p>}
        </Card>
      </div>
      {editing && selected && <PriceDialog productId={selected.id} productName={selected.name} current={selected.current}
        onClose={() => setEditing(false)} onSaved={() => { setEditing(false); setVersion((v) => v + 1) }} />}
    </AdminPage>
  )
}
