import { useCallback, useState } from 'react'
import { admin, type ProductRow } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox } from '../../components/ui'
import { dateTime, qty } from '../../format'
import { Pager } from '../desk/deskUi'
import { AdminPage, Card, DataTable, Field, FilterBar, Flash, Loaded, Modal, SearchBox, Select, TextInput, type FlashMessage } from './adminUi'
import { useAction, useCatalogueOptions } from './adminHooks'
import { StockText, Thumb } from './ProductPages'

const LIMIT = 20
const MOVEMENT_LABELS = { ORDER_DEDUCTION: 'Order', RESTOCK: 'Restock', ADJUSTMENT: 'Adjustment' }

export function StockDialog({ product, onClose, onSaved }: { product: Pick<ProductRow, 'id' | 'name' | 'sku' | 'stock'>; onClose: () => void; onSaved: () => void }) {
  const token = useToken()
  const action = useAction()
  const [mode, setMode] = useState<'add' | 'remove' | 'set'>('add')
  const [quantity, setQuantity] = useState('')
  const [reason, setReason] = useState('')
  const current = Number(product.stock ?? 0)
  const n = Number(quantity)
  const next = mode === 'add' ? current + n : mode === 'remove' ? current - n : n
  const valid = /^\d+(\.\d{1,3})?$/.test(quantity) && reason.trim() && next >= 0 && next !== current

  return (
    <Modal title={`Update stock: ${product.name}`} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={async () => {
        if (await action.run(() => admin.adjustStock(token, product.id, { mode, quantity, reason: reason.trim() }))) onSaved()
      }}>Save</Button>
    </>}>
      <p className="text-sm text-ink">In stock now: <b>{qty(current)} cases</b></p>
      <Select label="Change" value={mode} onChange={(v) => setMode(v as typeof mode)} options={[['add', 'Add stock (restock)'], ['remove', 'Remove stock (damage, loss, return)'], ['set', 'Set to counted stock']]} />
      <Field label={mode === 'set' ? 'Counted stock (cases)' : 'Cases'}><TextInput value={quantity} onChange={setQuantity} inputMode="decimal" /></Field>
      <Field label="Reason (required, kept in the stock history)"><TextInput value={reason} onChange={setReason} maxLength={200} placeholder="e.g. Truck from Sunrise Foods, invoice 1234" /></Field>
      {quantity && <p className={`text-sm font-semibold ${next < 0 ? 'text-red-700' : 'text-ink'}`}>{next < 0 ? 'Stock cannot go below 0' : `New stock: ${qty(next)} cases`}</p>}
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

export function StockPage() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [filter, setFilter] = useState(() => new URLSearchParams(window.location.search).get('filter') ?? '')
  const [page, setPage] = useState(1)
  const [adjusting, setAdjusting] = useState<ProductRow | null>(null)
  const [history, setHistory] = useState<string | null>(() => new URLSearchParams(window.location.search).get('product'))
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [version, setVersion] = useState(0)
  const { categories } = useCatalogueOptions()
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.stock(t, { search, category_id: category, stock: filter, page, limit: LIMIT }, s),
    `${search}|${category}|${filter}|${page}|${version}`)

  return (
    <AdminPage title="Stock" subtitle="Current stock per product. Every change is recorded with the stock before and after, who made it and why.">
      <Flash message={flash} onClose={() => setFlash(null)} />
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search product, SKU or brand" />
        <Select label="Category" value={category} onChange={(v) => { setCategory(v); setPage(1) }} options={[['', 'All'], ...categories.map((c) => [c.id, c.name] as [string, string])]} />
        <Select label="Show" value={filter} onChange={(v) => { setFilter(v); setPage(1) }} options={[['', 'All products'], ['low', 'Low stock'], ['out', 'Out of stock']]} />
      </FilterBar>
      <div className={`grid gap-5 ${history ? '2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : ''}`}>
        <Loaded state={list.state} reload={list.reload}>
          {(d) => (
            <div>
              <DataTable rows={d.items} rowKey={(p) => p.id} loading={list.loading} empty="No products match" columns={[
                { header: 'Product', cell: (p) => <span className="flex items-center gap-3"><Thumb p={p} /><span><span className="block font-semibold text-ink">{p.name}</span><span className="text-xs text-ink-soft">{p.sku}</span></span></span> },
                { header: 'Stock', align: 'right', cell: (p) => <StockText stock={p.stock} low={d.low_stock} /> },
                { header: 'Last updated', cell: (p) => (p.last_movement_at ? dateTime(p.last_movement_at) : '—'), wide: true },
                { header: '', cell: (p) => (
                  <span className="flex gap-3">
                    <button type="button" className="font-bold text-leaf-700 underline" onClick={() => setAdjusting(p)}>Update</button>
                    <button type="button" className="font-bold text-ink-soft underline" onClick={() => setHistory(p.id)}>History</button>
                  </span>
                ) },
              ]} />
              <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
              <p className="mt-1 text-xs text-ink-soft">Low stock = {qty(d.low_stock)} cases or fewer (Settings).</p>
            </div>
          )}
        </Loaded>
        {history && (
          <Card title="Stock history" actions={<><Link to={`/admin/products/${history}`} className="text-sm font-bold text-leaf-700">Product →</Link><button type="button" className="text-sm font-bold text-ink-soft" onClick={() => setHistory(null)}>Close</button></>} padded={false}>
            <StockHistory key={`${history}-${version}`} productId={history} />
          </Card>
        )}
      </div>
      {adjusting && <StockDialog product={adjusting} onClose={() => setAdjusting(null)}
        onSaved={() => { setFlash({ tone: 'success', text: `Stock updated for ${adjusting.name}` }); setAdjusting(null); setHistory(adjusting.id); setVersion((v) => v + 1) }} />}
    </AdminPage>
  )
}

function StockHistory({ productId }: { productId: string }) {
  const rows = useLoad((t, s) => admin.stockHistory(t, productId, s), `stock-history-${productId}`)
  return (
    <Loaded state={rows.state} reload={rows.reload}>
      {(items) => (
        <DataTable rows={items} rowKey={(m) => m.id} empty="No stock movements" columns={[
          { header: 'When', cell: (m) => dateTime(m.at) },
          { header: 'Type', cell: (m) => MOVEMENT_LABELS[m.type] },
          { header: 'Before → after', align: 'right', cell: (m) => (m.stock_before !== null ? `${qty(m.stock_before)} → ${qty(m.stock_after!)}` : '—') },
          { header: 'Change', align: 'right', cell: (m) => <span className={Number(m.change) < 0 ? 'text-red-700' : 'text-leaf-700'}>{Number(m.change) > 0 ? '+' : ''}{qty(m.change)}</span> },
          { header: 'Reason', cell: (m) => (m.order_id ? <Link to={`/desk/orders/${m.order_id}`} className="text-leaf-700">{m.order_number}</Link> : m.reason ?? '—') },
          { header: 'By', cell: (m) => m.by ?? '—', wide: true },
        ]} />
      )}
    </Loaded>
  )
}
