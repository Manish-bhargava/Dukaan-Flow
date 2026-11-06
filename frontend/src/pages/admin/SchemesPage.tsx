import { useCallback, useState } from 'react'
import { admin, type ProductRow, type SchemeRow } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox, Notice } from '../../components/ui'
import { dateTime } from '../../format'
import { Pager } from '../desk/deskUi'
import { SCHEME_STATE_TONE } from './adminFormat'
import {
  AdminPage, Checkbox, ConfirmDialog, DataTable, Field, FilterBar, Flash, Loaded, Modal, Pill, SearchBox, Select, Tabs, TextInput,
  type FlashMessage,
} from './adminUi'
import { useAction } from './adminHooks'

const LIMIT = 20
type State = 'all' | 'active' | 'upcoming' | 'expired' | 'inactive'
const toLocal = (iso: string | null) => (iso ? new Date(new Date(iso).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '')
const fromLocal = (v: string) => (v ? new Date(v).toISOString() : null)

export function SchemesPage() {
  const [state, setState] = useState<State>('active')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<SchemeRow | 'new' | null>(null)
  const [toggling, setToggling] = useState<SchemeRow | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [version, setVersion] = useState(0)
  const token = useToken()
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.schemes(t, { state, search, page, limit: LIMIT }, s), `${state}|${search}|${page}|${version}`)
  const saved = (text: string) => { setEditing(null); setToggling(null); setFlash({ tone: 'success', text }); setVersion((v) => v + 1) }

  return (
    <AdminPage title="Schemes" subtitle="Buy X get Y free and percentage discounts. The same scheme engine prices retailer, salesman and order desk orders."
      actions={<Button onClick={() => setEditing('new')}>+ New scheme</Button>}>
      <Flash message={flash} onClose={() => setFlash(null)} />
      <Tabs value={state} onChange={(v) => { setState(v); setPage(1) }} tabs={[['active', 'Active'], ['upcoming', 'Upcoming'], ['expired', 'Expired'], ['inactive', 'Inactive'], ['all', 'All']]} />
      <FilterBar><SearchBox value={search} onChange={onSearch} placeholder="Search product, SKU or brand" /></FilterBar>
      <Loaded state={list.state} reload={list.reload}>
        {(d) => (
          <>
            <DataTable rows={d.items} rowKey={(s) => s.id} loading={list.loading} empty="No schemes here" columns={[
              { header: 'Product', cell: (s) => <Link to={`/admin/products/${s.product.id}`} className="font-semibold text-ink hover:text-leaf-700">{s.product.name}<span className="block text-xs font-normal text-ink-soft">{s.product.sku}</span></Link> },
              { header: 'Scheme', cell: (s) => <span className="font-bold text-mango-600">{s.description}</span> },
              { header: 'Type', cell: (s) => (s.scheme_type === 'FREE_GOODS' ? 'Buy X get Y' : '% discount'), wide: true },
              { header: 'Starts', cell: (s) => dateTime(s.starts_at) },
              { header: 'Ends', cell: (s) => (s.ends_at ? dateTime(s.ends_at) : 'No end') },
              { header: 'State', cell: (s) => <Pill tone={SCHEME_STATE_TONE[s.state]}>{s.state}</Pill> },
              { header: '', cell: (s) => (
                <span className="flex gap-3">
                  <button type="button" className="font-bold text-leaf-700 underline" onClick={() => setEditing(s)}>Edit</button>
                  <button type="button" className="font-bold text-ink-soft underline" onClick={() => setToggling(s)}>{s.is_active ? 'Deactivate' : 'Activate'}</button>
                </span>
              ) },
            ]} />
            <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </Loaded>
      {editing && <SchemeForm scheme={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSaved={saved} />}
      {toggling && (
        <ConfirmDialog title={toggling.is_active ? 'Deactivate scheme?' : 'Activate scheme?'} danger={toggling.is_active}
          confirmLabel={toggling.is_active ? 'Deactivate' : 'Activate'} onClose={() => setToggling(null)}
          message={`${toggling.product.name}: ${toggling.description}. ${toggling.is_active ? 'New orders stop getting it; placed orders keep their scheme.' : 'New orders get it while it is in its dates.'}`}
          onConfirm={async () => { await admin.updateScheme(token, toggling.id, { is_active: !toggling.is_active }); saved('Scheme updated') }} />
      )}
    </AdminPage>
  )
}

function SchemeForm({ scheme, onClose, onSaved }: { scheme?: SchemeRow; onClose: () => void; onSaved: (text: string) => void }) {
  const token = useToken()
  const action = useAction()
  const [type, setType] = useState(scheme?.scheme_type ?? 'FREE_GOODS')
  const [minQty, setMinQty] = useState(scheme ? String(Number(scheme.min_quantity)) : '')
  const [benefit, setBenefit] = useState(scheme ? String(Number(scheme.scheme_type === 'FREE_GOODS' ? scheme.free_quantity : scheme.discount_percentage)) : '')
  const [starts, setStarts] = useState(() => toLocal(scheme?.starts_at ?? new Date().toISOString()))
  const [ends, setEnds] = useState(toLocal(scheme?.ends_at ?? null))
  const [products, setProducts] = useState<ProductRow[]>([])
  const [search, setSearch] = useState('')
  const options = useLoad((t, s) => admin.products(t, { search, status: 'active', limit: 20 }, s), `scheme-products|${search}`)
  const num = (v: string) => /^\d+(\.\d+)?$/.test(v) && Number(v) > 0
  const valid = num(minQty) && num(benefit) && (type === 'FREE_GOODS' || Number(benefit) <= 100) && starts && (scheme || products.length)
    && (!ends || new Date(ends) > new Date(starts))
  const preview = type === 'FREE_GOODS' ? `Buy ${minQty || 'X'} get ${benefit || 'Y'} free` : `${benefit || 'N'}% off on ${minQty || 'X'}+`

  async function save() {
    const benefitFields = type === 'FREE_GOODS' ? { free_quantity: benefit, discount_percentage: '0' } : { discount_percentage: benefit, free_quantity: '0' }
    const dates = { starts_at: fromLocal(starts), ends_at: fromLocal(ends) }
    if (scheme) {
      if (await action.run(() => admin.updateScheme(token, scheme.id, { min_quantity: minQty, ...benefitFields, ...dates }))) onSaved('Scheme saved')
    } else if (await action.run(() => admin.createSchemes(token, { product_ids: products.map((p) => p.id), scheme_type: type, min_quantity: minQty, ...benefitFields, ...dates }))) {
      onSaved(products.length === 1 ? 'Scheme created' : `Scheme created for ${products.length} products`)
    }
  }

  return (
    <Modal title={scheme ? `Edit scheme: ${scheme.product.name}` : 'New scheme'} onClose={onClose} wide footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>{scheme ? 'Save' : 'Create'}</Button>
    </>}>
      {!scheme && (
        <Select label="Type" value={type} onChange={(v) => setType(v as typeof type)} options={[['FREE_GOODS', 'Buy X get Y free (cases)'], ['SLAB_DISCOUNT', 'Percentage discount from a quantity']]} />
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Minimum quantity (cases)"><TextInput value={minQty} onChange={setMinQty} inputMode="decimal" /></Field>
        <Field label={type === 'FREE_GOODS' ? 'Free cases per minimum' : 'Discount %'}><TextInput value={benefit} onChange={setBenefit} inputMode="decimal" /></Field>
        <Field label="Starts"><TextInput type="datetime-local" value={starts} onChange={setStarts} /></Field>
        <Field label="Ends (optional)"><TextInput type="datetime-local" value={ends} onChange={setEnds} /></Field>
      </div>
      <Notice>Preview: <b>{preview}</b>. A product can have only one active scheme at a time (schemes are never combined).</Notice>
      {!scheme && (
        <div>
          <p className="text-xs font-bold text-ink-soft">Eligible products ({products.length} chosen)</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {products.map((p) => (
              <button key={p.id} type="button" onClick={() => setProducts(products.filter((x) => x.id !== p.id))}
                className="rounded-full bg-leaf-50 px-2.5 py-1 text-xs font-bold text-leaf-800">{p.name} ✕</button>
            ))}
          </div>
          <div className="mt-2"><SearchBox value={search} onChange={setSearch} placeholder="Find products to add" /></div>
          <div className="mt-2 max-h-56 overflow-y-auto rounded-xl border border-gray-200">
            {options.state.status === 'ready' && options.state.data.items.map((p) => (
              <div key={p.id} className="border-b border-gray-100 px-3 py-2 last:border-0">
                <Checkbox checked={products.some((x) => x.id === p.id)} onChange={(on) => setProducts(on ? [...products, p] : products.filter((x) => x.id !== p.id))}>
                  {p.name} <span className="font-normal text-ink-soft">{p.sku}</span>
                </Checkbox>
              </div>
            ))}
          </div>
        </div>
      )}
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

