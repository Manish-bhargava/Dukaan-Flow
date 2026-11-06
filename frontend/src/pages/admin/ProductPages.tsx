import { useCallback, useRef, useState } from 'react'
import { admin, uploadProductImage, type PriceBasis, type ProductDetail, type ProductRow } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { PackShot } from '../../components/PackShot'
import { Button, ErrorBox } from '../../components/ui'
import { dateTime, qty, rupees } from '../../format'
import { navigate } from '../../router'
import { Pager } from '../desk/deskUi'
import { SCHEME_STATE_TONE } from './adminFormat'
import {
  ActivePill, AdminPage, Card, Checkbox, ConfirmDialog, DataTable, Field, FilterBar, Flash, KeyValues, Loaded, Modal, Pill,
  SearchBox, Select, TextInput, type FlashMessage,
} from './adminUi'
import { PriceDialog, PriceHistory } from './PricingPage'
import { StockDialog } from './StockPage'
import { useAction, useCatalogueOptions } from './adminHooks'

const LIMIT = 20
const param = (key: string) => new URLSearchParams(window.location.search).get(key) ?? ''

export function Thumb({ p }: { p: Pick<ProductRow, 'thumbnail_url' | 'name' | 'brand' | 'pack_size' | 'category'> }) {
  return p.thumbnail_url
    ? <img src={p.thumbnail_url} alt="" className="h-10 w-10 shrink-0 rounded-lg border border-gray-100 object-contain" />
    : <span className="block h-10 w-10 shrink-0 overflow-hidden rounded-lg"><PackShot name={p.name} brand={p.brand} packSize={p.pack_size} category={p.category.name} /></span>
}

export function ProductsPage() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [brand, setBrand] = useState('')
  const [status, setStatus] = useState('')
  const [stock, setStock] = useState(param('stock'))
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const options = useCatalogueOptions()
  const reset = (set: (v: string) => void) => (v: string) => { set(v); setPage(1) }
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.products(t, { search, category_id: category, brand, status, stock, page, limit: LIMIT }, s),
    `${search}|${category}|${brand}|${status}|${stock}|${page}`)

  return (
    <AdminPage title="Products" subtitle="The one catalogue used by retailers, salesmen and the order desk."
      actions={<Button onClick={() => setCreating(true)}>+ Add product</Button>}>
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search name, SKU or brand" />
        <Select label="Category" value={category} onChange={reset(setCategory)} options={[['', 'All'], ...options.categories.map((c) => [c.id, c.name] as [string, string])]} />
        <Select label="Brand" value={brand} onChange={reset(setBrand)} options={[['', 'All'], ...options.brands.map((b) => [b.name, b.name] as [string, string])]} />
        <Select label="Status" value={status} onChange={reset(setStatus)} options={[['', 'All'], ['active', 'Active'], ['inactive', 'Inactive']]} />
        <Select label="Stock" value={stock} onChange={reset(setStock)} options={[['', 'All'], ['low', 'Low'], ['out', 'Out of stock']]} />
      </FilterBar>
      <Loaded state={list.state} reload={list.reload}>
        {(d) => (
          <>
            <DataTable rows={d.items} rowKey={(p) => p.id} loading={list.loading} onRow={(p) => navigate(`/admin/products/${p.id}`)} empty="No products match" columns={[
              { header: 'Product', cell: (p) => <span className="flex items-center gap-3"><Thumb p={p} /><span className="min-w-0"><span className="block font-semibold text-ink">{p.name}</span><span className="text-xs text-ink-soft">{p.sku}</span></span></span> },
              { header: 'Brand', cell: (p) => p.brand },
              { header: 'Category', cell: (p) => p.category.name, wide: true },
              { header: 'Pack', cell: (p) => `${p.pack_size} · ${qty(p.units_per_case)}/${p.order_unit}`, wide: true },
              { header: 'Default price', align: 'right', cell: (p) => (p.default_price ? `${rupees(p.default_price.dealer_price)} / ${p.default_price.price_basis.toLowerCase()}` : '—') },
              { header: 'Stock', align: 'right', cell: (p) => <StockText stock={p.stock} low={d.low_stock} /> },
              { header: 'Status', cell: (p) => <ActivePill active={p.is_active} /> },
            ]} />
            <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </Loaded>
      {creating && <ProductForm onClose={() => setCreating(false)} onSaved={(id) => navigate(`/admin/products/${id}`)} />}
    </AdminPage>
  )
}

export function StockText({ stock, low }: { stock: string | null; low: number }) {
  const n = Number(stock ?? 0)
  return <span className={`font-bold ${n <= 0 ? 'text-red-700' : n <= low ? 'text-mango-600' : 'text-ink'}`}>{n <= 0 ? 'Out' : `${qty(n)} cases`}</span>
}

function ProductForm({ product, onClose, onSaved }: { product?: ProductDetail; onClose: () => void; onSaved: (id: string) => void }) {
  const token = useToken()
  const action = useAction()
  const { categories, brands } = useCatalogueOptions()
  const [f, setF] = useState({
    sku: product?.sku ?? '', name: product?.name ?? '', brand: product?.brand ?? '', category_id: product?.category.id ?? '',
    pack_size: product?.pack_size ?? '', units_per_case: product ? String(Number(product.units_per_case)) : '',
    base_unit: product?.base_unit ?? 'piece', order_unit: product?.order_unit ?? 'case', gst_rate: product ? String(Number(product.gst_rate)) : '18',
    price: '', price_basis: 'PIECE' as PriceBasis, tax_inclusive: false, opening_stock: '0',
  })
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v })
  const num = (v: string) => /^\d+(\.\d+)?$/.test(v)
  const valid = f.sku.trim() && f.name.trim() && f.brand && f.category_id && f.pack_size.trim() && num(f.units_per_case) && Number(f.units_per_case) > 0
    && num(f.gst_rate) && (product || ((!f.price || num(f.price)) && num(f.opening_stock)))

  async function save() {
    const base = { sku: f.sku, name: f.name, brand: f.brand, category_id: f.category_id, pack_size: f.pack_size,
      units_per_case: f.units_per_case, base_unit: f.base_unit, order_unit: f.order_unit, gst_rate: f.gst_rate }
    if (product) {
      if (await action.run(() => admin.updateProduct(token, product.id, base))) onSaved(product.id)
      return
    }
    let id = ''
    const body = { ...base, opening_stock: f.opening_stock || '0',
      default_price: f.price ? { dealer_price: f.price, price_basis: f.price_basis, tax_inclusive: f.tax_inclusive } : null }
    if (await action.run(async () => { id = (await admin.createProduct(token, body)).data.id })) onSaved(id)
  }

  return (
    <Modal title={product ? 'Edit product' : 'Add product'} onClose={onClose} wide footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>{product ? 'Save changes' : 'Create product'}</Button>
    </>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="SKU / code"><TextInput value={f.sku} onChange={(v) => set('sku')(v.toUpperCase())} maxLength={50} /></Field>
        <Field label="Product name"><TextInput value={f.name} onChange={set('name')} maxLength={200} placeholder="e.g. Glucose Biscuit 75g" /></Field>
        <Select label="Brand" value={f.brand} onChange={set('brand')} options={[['', 'Choose…'], ...brands.filter((b) => b.is_active || b.name === f.brand).map((b) => [b.name, b.name] as [string, string])]} />
        <Select label="Category" value={f.category_id} onChange={set('category_id')} options={[['', 'Choose…'], ...categories.map((c) => [c.id, c.name + (c.is_active ? '' : ' (inactive)')] as [string, string])]} />
        <Field label="Pack size"><TextInput value={f.pack_size} onChange={set('pack_size')} placeholder="e.g. 75g" maxLength={100} /></Field>
        <Field label="Units per case"><TextInput value={f.units_per_case} onChange={set('units_per_case')} inputMode="decimal" /></Field>
        <Field label="Base unit"><TextInput value={f.base_unit} onChange={set('base_unit')} maxLength={30} /></Field>
        <Field label="Order unit" hint="Retailers and salesmen order in this unit"><TextInput value={f.order_unit} onChange={set('order_unit')} maxLength={30} /></Field>
        <Field label="GST %"><TextInput value={f.gst_rate} onChange={set('gst_rate')} inputMode="decimal" /></Field>
        {!product && <>
          <Field label="Opening stock (cases)"><TextInput value={f.opening_stock} onChange={set('opening_stock')} inputMode="decimal" /></Field>
          <Field label="Default dealer price (₹, optional)" hint="Without a price the product is not sold until one is set"><TextInput value={f.price} onChange={set('price')} inputMode="decimal" /></Field>
          <Select label="Price per" value={f.price_basis} onChange={(v) => setF({ ...f, price_basis: v as PriceBasis })} options={[['PIECE', 'Piece'], ['CASE', 'Case']]} />
          <Checkbox checked={f.tax_inclusive} onChange={(v) => setF({ ...f, tax_inclusive: v })}>Price includes GST</Checkbox>
        </>}
      </div>
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

export function ProductDetailPage({ productId }: { productId: string }) {
  const token = useToken()
  const detail = useLoad((t, s) => admin.product(t, productId, s), `admin-product-${productId}`)
  const [dialog, setDialog] = useState<'edit' | 'price' | 'stock' | 'status' | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [version, setVersion] = useState(0)
  const file = useRef<HTMLInputElement>(null)
  const upload = useAction()
  const done = (text: string) => () => { setDialog(null); setFlash({ tone: 'success', text }); detail.reload(); setVersion((v) => v + 1) }

  return (
    <Loaded state={detail.state} reload={detail.reload} label="Loading product…">
      {(p) => (
        <AdminPage title={p.name} back={<Link to="/admin/products">← Products</Link>}
          subtitle={<span className="flex flex-wrap items-center gap-2">{p.sku} · {p.brand} · {p.category.name} <ActivePill active={p.is_active} /></span>}
          actions={<>
            <Button variant="secondary" onClick={() => setDialog('edit')}>Edit</Button>
            <Button variant="secondary" onClick={() => setDialog('stock')}>Update stock</Button>
            <Button variant={p.is_active ? 'danger' : 'primary'} onClick={() => setDialog('status')}>{p.is_active ? 'Deactivate' : 'Activate'}</Button>
          </>}>
          <Flash message={flash} onClose={() => setFlash(null)} />
          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Image">
              <div className="mx-auto aspect-square max-w-[220px] overflow-hidden rounded-xl border border-gray-100 bg-white">
                {p.image_url ? <img src={p.image_url} alt={p.name} className="h-full w-full object-contain" /> : <PackShot name={p.name} brand={p.brand} packSize={p.pack_size} category={p.category.name} />}
              </div>
              <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={async (e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f && await upload.run(() => uploadProductImage(token, p.id, f))) done('Image updated')()
              }} />
              <Button variant="secondary" className="mt-3 w-full" busy={upload.busy} onClick={() => file.current?.click()}>{p.image_url ? 'Replace image' : 'Upload image'}</Button>
              {upload.error && <div className="mt-2"><ErrorBox message={upload.error} /></div>}
            </Card>
            <Card title="Details">
              <KeyValues rows={[['SKU', p.sku], ['Brand', p.brand], ['Category', p.category.name], ['Pack size', p.pack_size],
                ['Case', `${qty(p.units_per_case)} ${p.base_unit}s per ${p.order_unit}`], ['GST', `${qty(p.gst_rate)}%`], ['Updated', dateTime(p.updated_at)]]} />
            </Card>
            <Card title="Stock & price">
              <KeyValues rows={[
                ['In stock', <StockText key="s" stock={p.stock} low={p.low_stock} />],
                ['Stock updated', p.stock_updated_at ? dateTime(p.stock_updated_at) : '—'],
                ['Default price', p.default_price ? `${rupees(p.default_price.dealer_price)} / ${p.default_price.price_basis.toLowerCase()}${p.default_price.tax_inclusive ? ' incl. GST' : ' + GST'}` : 'Not set'],
              ]} />
              <Button className="mt-3 w-full" variant="secondary" onClick={() => setDialog('price')}>Set default price</Button>
            </Card>
          </div>
          <Card title="Price history" actions={<Link to="/admin/pricing" className="text-sm font-bold text-leaf-700">Pricing →</Link>}>
            <PriceHistory key={version} productId={p.id} />
          </Card>
          <div className="grid gap-5 xl:grid-cols-2">
            <Card title="Schemes" actions={<Link to="/admin/schemes" className="text-sm font-bold text-leaf-700">Manage schemes →</Link>} padded={false}>
              <DataTable rows={p.schemes} rowKey={(s) => s.id} empty="No schemes" columns={[
                { header: 'Scheme', cell: (s) => s.description },
                { header: 'From', cell: (s) => dateTime(s.starts_at) },
                { header: 'Until', cell: (s) => (s.ends_at ? dateTime(s.ends_at) : 'No end') },
                { header: 'State', cell: (s) => <Pill tone={SCHEME_STATE_TONE[s.state]}>{s.state}</Pill> },
              ]} />
            </Card>
            <Card title="Recent stock movements" actions={<Link to={`/admin/stock?product=${p.id}`} className="text-sm font-bold text-leaf-700">Full history →</Link>} padded={false}>
              <DataTable rows={p.movements} rowKey={(m) => m.id} empty="No stock movements" columns={[
                { header: 'When', cell: (m) => dateTime(m.at) },
                { header: 'Change', align: 'right', cell: (m) => <span className={Number(m.change) < 0 ? 'text-red-700' : 'text-leaf-700'}>{Number(m.change) > 0 ? '+' : ''}{qty(m.change)}</span> },
                { header: 'Stock after', align: 'right', cell: (m) => (m.stock_after ? qty(m.stock_after) : '—') },
                { header: 'Reason', cell: (m) => m.order_number ?? m.reason ?? '—', wide: true },
              ]} />
            </Card>
          </div>
          {dialog === 'edit' && <ProductForm product={p} onClose={() => setDialog(null)} onSaved={done('Product saved')} />}
          {dialog === 'price' && <PriceDialog productId={p.id} productName={p.name} current={p.default_price} onClose={() => setDialog(null)} onSaved={done('Default price saved')} />}
          {dialog === 'stock' && <StockDialog product={p} onClose={() => setDialog(null)} onSaved={done('Stock updated')} />}
          {dialog === 'status' && (
            <ConfirmDialog title={p.is_active ? 'Deactivate product?' : 'Activate product?'} danger={p.is_active}
              confirmLabel={p.is_active ? 'Deactivate' : 'Activate'} onClose={() => setDialog(null)}
              message={p.is_active ? `${p.name} disappears from every catalogue and open orders containing it cannot be confirmed until corrected. Past orders keep it.` : `${p.name} returns to the catalogues (where it has a price).`}
              onConfirm={async () => { await admin.updateProduct(token, p.id, { is_active: !p.is_active }); done(p.is_active ? 'Product deactivated' : 'Product activated')() }} />
          )}
        </AdminPage>
      )}
    </Loaded>
  )
}
