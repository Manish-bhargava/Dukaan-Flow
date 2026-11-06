import { useCallback, useState } from 'react'
import { admin, type RetailerDetail, type RetailerPriceRow, type RetailerRow } from '../../api/admin'
import { listDeskOrders } from '../../api/orderDesk'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox, Notice, SourceBadge, StatusBadge } from '../../components/ui'
import { creditLevel, CREDIT_LEVEL_STYLES, dateTime, rupees } from '../../format'
import { navigate } from '../../router'
import { Pager } from '../desk/deskUi'
import { ACTION_LABELS, describeChange } from './adminFormat'
import {
  ActivePill, AdminPage, Card, Checkbox, ConfirmDialog, DataTable, Field, FilterBar, Flash, KeyValues, Loaded, Modal, Pill,
  SearchBox, Select, Tabs, TextInput, type FlashMessage,
} from './adminUi'
import { PriceDialog } from './PricingPage'
import { useAction, useSalesmanOptions } from './adminHooks'

const LIMIT = 20
const param = (key: string) => new URLSearchParams(window.location.search).get(key) ?? ''

export function RetailersPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(param('status'))
  const [salesman, setSalesman] = useState(param('salesman'))
  const [sort, setSort] = useState(param('sort') || 'name')
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const salesmen = useSalesmanOptions()
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1) }
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.retailers(t, { search, status, salesman_id: salesman, sort, page, limit: LIMIT }, s),
    `${search}|${status}|${salesman}|${sort}|${page}`)

  return (
    <AdminPage title="Retailers" subtitle="Shops, their salesman, credit and status."
      actions={<Button onClick={() => setCreating(true)}>+ Add retailer</Button>}>
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search shop, owner, mobile, city or ID" />
        <Select label="Status" value={status} onChange={reset(setStatus)} options={[['', 'All'], ['active', 'Active'], ['inactive', 'Inactive'], ['restricted', 'Ordering paused']]} />
        <Select label="Salesman" value={salesman} onChange={reset(setSalesman)} options={salesmen} />
        <Select label="Sort" value={sort} onChange={reset(setSort)} options={[['name', 'Name'], ['newest', 'Newest'], ['outstanding', 'Highest outstanding'], ['last_order', 'Last order'], ['purchased', 'Most purchased']]} />
      </FilterBar>
      <Loaded state={list.state} reload={list.reload}>
        {(data) => (
          <>
            <DataTable rows={data.items} rowKey={(r) => r.id} loading={list.loading} onRow={(r) => navigate(`/admin/retailers/${r.id}`)}
              empty="No retailers match" columns={retailerColumns} />
            <Pager page={page} total={data.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </Loaded>
      {creating && <RetailerForm onClose={() => setCreating(false)} onSaved={(id) => navigate(`/admin/retailers/${id}`)} />}
    </AdminPage>
  )
}

const retailerColumns = [
  { header: 'Retailer', cell: (r: RetailerRow) => <><span className="font-semibold text-ink">{r.shop_name}</span><span className="block text-xs text-ink-soft">{r.owner_name} · {r.phone}</span></> },
  { header: 'City', cell: (r: RetailerRow) => r.city, wide: true },
  { header: 'Salesman', cell: (r: RetailerRow) => r.salesman?.name ?? <span className="text-mango-600">Not assigned</span> },
  { header: 'Credit limit', align: 'right' as const, cell: (r: RetailerRow) => (r.credit_limit ? rupees(r.credit_limit) : '—') },
  { header: 'Outstanding', align: 'right' as const, cell: (r: RetailerRow) => (r.outstanding ? rupees(r.outstanding) : '—') },
  { header: 'Last order', cell: (r: RetailerRow) => (r.last_order_at ? dateTime(r.last_order_at) : 'Never'), wide: true },
  { header: 'Status', cell: (r: RetailerRow) => <span className="flex flex-wrap gap-1"><ActivePill active={r.is_active} />{r.ordering_restricted_reason && <Pill tone="red">Ordering paused</Pill>}</span> },
]

export function RetailerForm({ retailer, onClose, onSaved }: { retailer?: RetailerDetail; onClose: () => void; onSaved: (id: string) => void }) {
  const token = useToken()
  const salesmen = useSalesmanOptions(false)
  const action = useAction()
  const [f, setF] = useState({
    shop_name: retailer?.shop_name ?? '', owner_name: retailer?.owner_name ?? '', phone: retailer?.phone ?? '',
    email: retailer?.logins[0]?.email ?? '', address: retailer?.address ?? '', city: retailer?.city ?? 'Jabalpur',
    gstin: retailer?.gstin ?? '', salesman_id: retailer?.salesman?.id ?? '', credit_limit: '',
  })
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v })
  const valid = f.shop_name.trim() && f.owner_name.trim() && /^[6-9]\d{9}$/.test(f.phone) && f.address.trim() && f.city.trim()
    && (retailer || /^\d+(\.\d{1,2})?$/.test(f.credit_limit))

  async function save() {
    const body = { ...f, email: f.email.trim() || null, gstin: f.gstin.trim() || null, salesman_id: f.salesman_id || null }
    if (retailer) {
      const { credit_limit: _ignored, ...edit } = body
      void _ignored
      if (await action.run(() => admin.updateRetailer(token, retailer.id, edit))) onSaved(retailer.id)
    } else {
      let id = ''
      if (await action.run(async () => { id = (await admin.createRetailer(token, body)).data.id })) onSaved(id)
    }
  }

  return (
    <Modal title={retailer ? 'Edit retailer' : 'Add retailer'} onClose={onClose} wide footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>{retailer ? 'Save changes' : 'Create retailer'}</Button>
    </>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Shop name"><TextInput value={f.shop_name} onChange={set('shop_name')} maxLength={200} /></Field>
        <Field label="Owner name"><TextInput value={f.owner_name} onChange={set('owner_name')} maxLength={150} /></Field>
        <Field label="Mobile (login)" hint="10 digits; the retailer signs in with this number">
          <TextInput value={f.phone} onChange={(v) => set('phone')(v.replace(/\D/g, '').slice(0, 10))} inputMode="tel" />
        </Field>
        <Field label="Email (for login codes)" hint="One-time login codes are emailed here">
          <TextInput value={f.email} onChange={set('email')} type="email" maxLength={255} />
        </Field>
        <div className="sm:col-span-2"><Field label="Address"><TextInput value={f.address} onChange={set('address')} maxLength={500} /></Field></div>
        <Field label="City"><TextInput value={f.city} onChange={set('city')} maxLength={100} /></Field>
        <Field label="GSTIN (optional)"><TextInput value={f.gstin} onChange={(v) => set('gstin')(v.toUpperCase())} maxLength={20} /></Field>
        <Select label="Salesman" value={f.salesman_id} onChange={set('salesman_id')} options={[['', 'Not assigned'], ...salesmen.slice(1)]} />
        {!retailer && <Field label="Credit limit (₹)"><TextInput value={f.credit_limit} onChange={set('credit_limit')} inputMode="decimal" /></Field>}
      </div>
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

export function CreditDialog({ retailer, onClose, onSaved }: {
  retailer: { id: string; shop_name: string; ordering_restricted_reason: string | null; credit_limit: string | null }
  onClose: () => void; onSaved: () => void
}) {
  const token = useToken()
  const action = useAction()
  const [limit, setLimit] = useState(retailer.credit_limit ?? '')
  const [paused, setPaused] = useState(Boolean(retailer.ordering_restricted_reason))
  const [reason, setReason] = useState(retailer.ordering_restricted_reason ?? '')
  const limitChanged = limit !== (retailer.credit_limit ?? '') && /^\d+(\.\d{1,2})?$/.test(limit)
  const pauseChanged = paused !== Boolean(retailer.ordering_restricted_reason) || (paused && reason.trim() !== (retailer.ordering_restricted_reason ?? ''))
  const valid = (limitChanged || pauseChanged) && (!paused || reason.trim())

  async function save() {
    const body: Record<string, unknown> = {}
    if (limitChanged) body.credit_limit = limit
    if (pauseChanged) body.ordering_restricted = paused
    if (paused || reason.trim()) body.reason = reason.trim() || null
    if (await action.run(() => admin.updateCredit(token, retailer.id, body))) onSaved()
  }

  return (
    <Modal title={`Credit: ${retailer.shop_name}`} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>Save</Button>
    </>}>
      <Field label="Credit limit (₹)" hint="Orders above the available credit are refused (retailer) or held (salesman)">
        <TextInput value={limit} onChange={setLimit} inputMode="decimal" />
      </Field>
      <Checkbox checked={paused} onChange={setPaused}>Pause ordering for this shop (all channels)</Checkbox>
      {(paused || retailer.ordering_restricted_reason) && (
        <Field label={paused ? 'Reason (shown to the retailer and salesman)' : 'Note for allowing ordering again (optional)'}>
          <TextInput value={reason} onChange={setReason} maxLength={300} placeholder="e.g. Payment overdue" />
        </Field>
      )}
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

type Tab = 'overview' | 'orders' | 'prices' | 'credit'

export function RetailerDetailPage({ retailerId }: { retailerId: string }) {
  const token = useToken()
  const detail = useLoad((t, s) => admin.retailer(t, retailerId, s), `admin-retailer-${retailerId}`)
  const [tab, setTab] = useState<Tab>('overview')
  const [dialog, setDialog] = useState<'edit' | 'credit' | 'status' | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const done = (text: string) => () => { setDialog(null); setFlash({ tone: 'success', text }); detail.reload() }

  return (
    <Loaded state={detail.state} reload={detail.reload} label="Loading retailer…">
      {(r) => {
        const level = r.credit ? creditLevel(r.credit.available_credit, r.credit.credit_limit) : 'low'
        return (
          <AdminPage title={r.shop_name} back={<Link to="/admin/retailers">← Retailers</Link>}
            subtitle={<span className="flex flex-wrap items-center gap-2">{r.owner_name} · {r.city} <ActivePill active={r.is_active} />{r.ordering_restricted_reason && <Pill tone="red">Ordering paused</Pill>}</span>}
            actions={<>
              <Button variant="secondary" onClick={() => setDialog('edit')}>Edit</Button>
              <Button variant="secondary" onClick={() => setDialog('credit')}>Credit & ordering</Button>
              <Button variant={r.is_active ? 'danger' : 'primary'} onClick={() => setDialog('status')}>{r.is_active ? 'Deactivate' : 'Activate'}</Button>
            </>}>
            <Flash message={flash} onClose={() => setFlash(null)} />
            {r.ordering_restricted_reason && <Notice tone="warn">Ordering is paused: {r.ordering_restricted_reason}</Notice>}
            <Tabs value={tab} onChange={setTab} tabs={[['overview', 'Overview'], ['orders', 'Order history'], ['prices', 'Prices & schemes'], ['credit', 'Credit history']]} />
            {tab === 'overview' && (
              <div className="grid gap-5 lg:grid-cols-3">
                <Card title="Details">
                  <KeyValues rows={[
                    ['Retailer ID', <span key="id" className="break-all font-mono text-xs">{r.id}</span>], ['Shop', r.shop_name], ['Owner', r.owner_name],
                    ['Mobile', r.phone], ['Address', `${r.address}, ${r.city}`], ['GSTIN', r.gstin ?? '—'],
                    ['Salesman', r.salesman ? <Link key="s" to={`/admin/salesmen/${r.salesman.id}`} className="text-leaf-700">{r.salesman.name}</Link> : 'Not assigned'],
                    ['Added', dateTime(r.created_at)],
                  ]} />
                </Card>
                <Card title="Credit">
                  {r.credit ? <KeyValues rows={[
                    ['Credit limit', rupees(r.credit.credit_limit)], ['Outstanding', rupees(r.credit.current_outstanding)],
                    ['Held by orders under review', rupees(r.credit.reserved_for_review)],
                    ['Available', <span key="a" className={CREDIT_LEVEL_STYLES[level].text}>{rupees(r.credit.available_credit)}</span>],
                  ]} /> : <p className="text-sm text-ink-soft">No credit account.</p>}
                </Card>
                <Card title="Purchases">
                  <KeyValues rows={[
                    ['Total purchased', rupees(r.purchases.total_purchased)], ['Confirmed orders', r.purchases.confirmed_orders],
                    ['Open orders', r.purchases.open_orders], ['Rejected orders', r.purchases.rejected_orders], ['All orders', r.purchases.total_orders],
                  ]} />
                </Card>
                <Card title="Login">
                  {r.logins.map((u) => <KeyValues key={u.id} rows={[['Mobile', u.phone], ['Email', u.email ?? 'Not set (cannot receive login codes)'],
                    ['Status', <ActivePill key="s" active={u.is_active} />], ['Last login', u.last_login_at ? dateTime(u.last_login_at) : 'Never']]} />)}
                </Card>
                <div className="lg:col-span-2">
                  <Card title="Recent orders" padded={false}>
                    <OrderList orders={r.recent_orders} />
                  </Card>
                </div>
              </div>
            )}
            {tab === 'orders' && <RetailerOrders retailerId={r.id} />}
            {tab === 'prices' && <RetailerPrices retailer={r} />}
            {tab === 'credit' && <CreditHistory retailerId={r.id} />}
            {dialog === 'edit' && <RetailerForm retailer={r} onClose={() => setDialog(null)} onSaved={done('Retailer saved')} />}
            {dialog === 'credit' && <CreditDialog retailer={{ ...r, credit_limit: r.credit?.credit_limit ?? null }} onClose={() => setDialog(null)} onSaved={done('Credit settings saved')} />}
            {dialog === 'status' && (
              <ConfirmDialog title={r.is_active ? 'Deactivate retailer?' : 'Activate retailer?'} danger={r.is_active}
                confirmLabel={r.is_active ? 'Deactivate' : 'Activate'} onClose={() => setDialog(null)}
                message={r.is_active ? `${r.shop_name} will not be able to log in or place orders, and salesmen will no longer see it. Order history is kept.` : `${r.shop_name} can log in and order again.`}
                onConfirm={async () => { await admin.updateRetailer(token, r.id, { is_active: !r.is_active }); done(r.is_active ? 'Retailer deactivated' : 'Retailer activated')() }} />
            )}
          </AdminPage>
        )
      }}
    </Loaded>
  )
}

function OrderList({ orders }: { orders: RetailerDetail['recent_orders'] }) {
  if (orders.length === 0) return <p className="px-4 py-6 text-sm text-ink-soft">No orders yet.</p>
  return (
    <ul className="divide-y divide-gray-100">
      {orders.map((o) => (
        <li key={o.id}>
          <Link to={`/desk/orders/${o.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-gray-50">
            <span><span className="font-semibold text-ink">{o.order_number}</span><span className="block text-xs text-ink-soft">{dateTime(o.created_at)} · <SourceBadge source={o.source} /></span></span>
            <span className="text-right"><span className="block font-bold">{rupees(o.grand_total)}</span><StatusBadge status={o.status} /></span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function RetailerOrders({ retailerId }: { retailerId: string }) {
  const [page, setPage] = useState(1)
  const orders = useLoad((t, s) => listDeskOrders(t, { view: 'all', page, limit: LIMIT, retailer_id: retailerId }, s), `${retailerId}|${page}`)
  return (
    <Loaded state={orders.state} reload={orders.reload}>
      {(d) => (
        <>
          <DataTable rows={d.items} rowKey={(o) => o.id} onRow={(o) => navigate(`/desk/orders/${o.id}`)} empty="No orders yet" columns={[
            { header: 'Order', cell: (o) => <span className="font-semibold text-leaf-700">{o.order_number}</span> },
            { header: 'Placed', cell: (o) => dateTime(o.created_at) },
            { header: 'Source', cell: (o) => <SourceBadge source={o.source} /> },
            { header: 'Placed by', cell: (o) => o.created_by.name, wide: true },
            { header: 'Amount', align: 'right', cell: (o) => rupees(o.grand_total) },
            { header: 'Status', cell: (o) => <StatusBadge status={o.status} /> },
          ]} />
          <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
        </>
      )}
    </Loaded>
  )
}

function RetailerPrices({ retailer }: { retailer: RetailerDetail }) {
  const prices = useLoad((t, s) => admin.retailerPrices(t, retailer.id, s), `prices-${retailer.id}`)
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<RetailerPriceRow | null>(null)
  return (
    <Loaded state={prices.state} reload={prices.reload}>
      {(rows) => {
        const q = search.toLowerCase()
        const shown = rows.filter((r) => !q || `${r.product.name} ${r.product.sku} ${r.product.brand}`.toLowerCase().includes(q))
        return (
          <>
            <FilterBar><SearchBox value={search} onChange={setSearch} placeholder="Search product" /></FilterBar>
            <p className="text-sm text-ink-soft">{rows.filter((r) => r.own).length} retailer-specific prices; the other products use the default price. Schemes apply to every retailer.</p>
            <DataTable rows={shown} rowKey={(r) => r.product.id} empty="No products" columns={[
              { header: 'Product', cell: (r) => <><span className="font-semibold text-ink">{r.product.name}</span><span className="block text-xs text-ink-soft">{r.product.sku}</span></> },
              { header: 'Default price', align: 'right', cell: (r) => (r.default ? `${rupees(r.default.dealer_price)} / ${r.default.price_basis.toLowerCase()}` : '—') },
              { header: 'This retailer', align: 'right', cell: (r) => (r.own ? <span className="font-bold text-leaf-800">{rupees(r.own.dealer_price)} / {r.own.price_basis.toLowerCase()}</span> : <span className="text-ink-soft">Default</span>) },
              { header: 'Schemes', cell: (r) => r.schemes.join(', ') || '—', wide: true },
              { header: '', cell: (r) => <button type="button" onClick={() => setEditing(r)} className="font-bold text-leaf-700 underline">Set price</button> },
            ]} />
            {editing && <PriceDialog productId={editing.product.id} productName={editing.product.name} retailer={{ id: retailer.id, shop_name: retailer.shop_name }}
              current={editing.own ?? editing.default} hasOwn={Boolean(editing.own)} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); prices.reload() }} />}
          </>
        )
      }}
    </Loaded>
  )
}

function CreditHistory({ retailerId }: { retailerId: string }) {
  const history = useLoad((t, s) => admin.creditHistory(t, retailerId, s), `credit-${retailerId}`)
  return (
    <Loaded state={history.state} reload={history.reload}>
      {(h) => (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Card title="Credit ledger" padded={false}>
            <DataTable rows={h.ledger} rowKey={(e) => e.id} empty="No credit transactions" columns={[
              { header: 'Date', cell: (e) => dateTime(e.at) },
              { header: 'Type', cell: (e) => ({ ORDER_DEBIT: 'Order', PAYMENT_CREDIT: 'Payment', ADJUSTMENT: 'Adjustment' }[e.type] ?? e.type) },
              { header: 'Details', cell: (e) => e.description ?? e.order_number ?? '—', wide: true },
              { header: 'Amount', align: 'right', cell: (e) => <span className={Number(e.amount) < 0 ? 'text-leaf-700' : ''}>{rupees(e.amount)}</span> },
              { header: 'By', cell: (e) => e.by ?? '—', wide: true },
            ]} />
          </Card>
          <Card title="Limit and ordering changes">
            {h.changes.length === 0 ? <p className="text-sm text-ink-soft">No changes recorded.</p> : (
              <ul className="space-y-3 text-sm">
                {h.changes.map((c) => (
                  <li key={c.id}>
                    <p className="font-bold text-ink">{ACTION_LABELS[c.action] ?? c.action}</p>
                    <p className="text-ink">{describeChange(c)}</p>
                    <p className="text-xs text-ink-soft">{c.actor?.name ?? 'Unknown'} · {dateTime(c.at)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </Loaded>
  )
}
