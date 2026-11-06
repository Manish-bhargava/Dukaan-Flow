import { useCallback, useState } from 'react'
import { admin, type SalesmanRow, type SyncInfo } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox, Notice, StatusBadge } from '../../components/ui'
import { ago, dateTime, rupees } from '../../format'
import { navigate } from '../../router'
import {
  ActivePill, AdminPage, Card, Checkbox, ConfirmDialog, DataTable, FilterBar, Flash, KeyValues, Loaded, Pill, SearchBox, Select,
  Stat, Tabs, type FlashMessage,
} from './adminUi'
import { useAction } from './adminHooks'
import { UserForm } from './UsersPage'

export function SyncBadge({ sync }: { sync: SyncInfo | null }) {
  if (!sync?.last_sync_at) return <Pill tone="gray">Never synced</Pill>
  const waiting = sync.pending_orders + sync.pending_visits
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span className="text-xs text-ink-soft">Synced {ago(sync.last_sync_at)}</span>
      {sync.failed_orders > 0 && <Pill tone="red">{sync.failed_orders} failed</Pill>}
      {waiting > 0 && <Pill tone="amber">{waiting} waiting</Pill>}
    </span>
  )
}

export function SalesmenPage() {
  const list = useLoad((t, s) => admin.salesmen(t, s), 'admin-salesmen')
  const [creating, setCreating] = useState(false)
  return (
    <AdminPage title="Salesmen" subtitle="Field team: assigned shops, visits, orders and offline sync (last 30 days)."
      actions={<><Button variant="secondary" onClick={() => navigate('/admin/assignments')}>Assign retailers</Button><Button onClick={() => setCreating(true)}>+ Add salesman</Button></>}>
      <Loaded state={list.state} reload={list.reload}>
        {(rows) => (
          <DataTable rows={rows} rowKey={(r) => r.id} onRow={(r) => navigate(`/admin/salesmen/${r.id}`)} empty="No salesmen yet" columns={[
            { header: 'Salesman', cell: (r: SalesmanRow) => <><span className="font-semibold text-ink">{r.name}</span><span className="block text-xs text-ink-soft">{r.phone}</span></> },
            { header: 'Shops', align: 'right', cell: (r) => r.assigned_retailers },
            { header: 'Visits', align: 'right', cell: (r) => `${r.visits_30d} (${r.visits_with_order_30d} with order)` },
            { header: 'Orders', align: 'right', cell: (r) => `${r.orders_30d}${r.offline_orders_30d ? ` · ${r.offline_orders_30d} offline` : ''}` },
            { header: 'Confirmed value', align: 'right', cell: (r) => rupees(r.confirmed_value_30d) },
            { header: 'Last visit', cell: (r) => (r.last_visit_at ? dateTime(r.last_visit_at) : '—'), wide: true },
            { header: 'Sync', cell: (r) => <SyncBadge sync={r.sync} /> },
            { header: 'Status', cell: (r) => <ActivePill active={r.is_active} /> },
          ]} />
        )}
      </Loaded>
      {creating && <UserForm role="SALESMAN" onClose={() => setCreating(false)} onSaved={(u) => navigate(`/admin/salesmen/${u.id}`)} />}
    </AdminPage>
  )
}

type Tab = 'shops' | 'visits' | 'orders' | 'sync'

export function SalesmanDetailPage({ salesmanId }: { salesmanId: string }) {
  const token = useToken()
  const detail = useLoad((t, s) => admin.salesman(t, salesmanId, s), `admin-salesman-${salesmanId}`)
  const [tab, setTab] = useState<Tab>('shops')
  const [dialog, setDialog] = useState<'edit' | 'status' | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const done = (text: string) => { setDialog(null); setFlash({ tone: 'success', text }); detail.reload() }
  return (
    <Loaded state={detail.state} reload={detail.reload} label="Loading salesman…">
      {(s) => (
        <AdminPage title={s.name} back={<Link to="/admin/salesmen">← Salesmen</Link>}
          subtitle={<span className="flex flex-wrap items-center gap-2">{s.phone}{s.email ? ` · ${s.email}` : ''} <ActivePill active={s.is_active} /></span>}
          actions={<>
            <Button variant="secondary" onClick={() => navigate(`/admin/assignments?salesman=${s.id}`)}>Assign retailers</Button>
            <Button variant="secondary" onClick={() => setDialog('edit')}>Edit</Button>
            <Button variant={s.is_active ? 'danger' : 'primary'} onClick={() => setDialog('status')}>{s.is_active ? 'Deactivate' : 'Activate'}</Button>
          </>}>
          <Flash message={flash} onClose={() => setFlash(null)} />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat icon="store" label="Assigned shops" value={s.retailers.length} />
            <Stat icon="pin" label="Visits (30 days)" value={s.stats_30d.visits} hint={`${s.stats_30d.visits_with_order} with an order`} />
            <Stat icon="orders" label="Orders (30 days)" value={s.stats_30d.orders} hint={`${s.stats_30d.offline_orders} created offline`} />
            <Stat icon="rupee" label="Confirmed value" value={rupees(s.stats_30d.confirmed_value)} hint="Last 30 days" />
          </div>
          <Tabs value={tab} onChange={setTab} tabs={[['shops', `Assigned retailers (${s.retailers.length})`], ['visits', 'Visits'], ['orders', 'Orders'], ['sync', 'Sync & activity']]} />
          {tab === 'shops' && (
            <DataTable rows={s.retailers} rowKey={(r) => r.id} onRow={(r) => navigate(`/admin/retailers/${r.id}`)} empty="No retailers assigned" columns={[
              { header: 'Retailer', cell: (r) => <><span className="font-semibold text-ink">{r.shop_name}</span><span className="block text-xs text-ink-soft">{r.owner_name} · {r.phone}</span></> },
              { header: 'Address', cell: (r) => `${r.address}, ${r.city}`, wide: true },
              { header: 'Outstanding', align: 'right', cell: (r) => (r.outstanding ? rupees(r.outstanding) : '—') },
              { header: 'Status', cell: (r) => <ActivePill active={r.is_active} /> },
            ]} />
          )}
          {tab === 'visits' && (
            <DataTable rows={s.visits} rowKey={(v) => v.id} empty="No visits yet" columns={[
              { header: 'Shop', cell: (v) => <span className="font-semibold text-ink">{v.shop_name}</span> },
              { header: 'Started', cell: (v) => dateTime(v.started_at) },
              { header: 'Ended', cell: (v) => (v.ended_at ? dateTime(v.ended_at) : 'Open') },
              { header: 'Outcome', cell: (v) => (v.order_id ? <Link to={`/desk/orders/${v.order_id}`} className="text-leaf-700">{v.order_number}</Link> : v.outcome === 'NO_ORDER' ? 'No order' : '—') },
              { header: 'Order status', cell: (v) => (v.order_status ? <StatusBadge status={v.order_status} /> : '—'), wide: true },
            ]} />
          )}
          {tab === 'orders' && <Notice>Orders placed by {s.name}, online and offline: <Link to={`/admin/orders?salesman=${s.id}`} className="font-bold text-leaf-700 underline">open the order list filtered by this salesman</Link>.</Notice>}
          {tab === 'sync' && (
            <div className="grid gap-5 lg:grid-cols-2">
              <Card title="Offline sync">
                <KeyValues rows={[
                  ['Last data download', s.sync?.last_sync_at ? dateTime(s.sync.last_sync_at) : 'Never'],
                  ['Phone last reported', s.sync?.reported_at ? dateTime(s.sync.reported_at) : 'Never'],
                  ['Orders waiting on the phone', s.sync?.pending_orders ?? 0], ['Visits waiting', s.sync?.pending_visits ?? 0],
                  ['Orders failed to sync', s.sync?.failed_orders ?? 0], ['Last error', s.sync?.last_error ?? '—'],
                ]} />
                <p className="mt-3 text-xs text-ink-soft">Waiting and failed orders live on the salesman’s phone; the phone reports them after each sync.</p>
              </Card>
              <Card title="Activity">
                <KeyValues rows={[['Last login', s.last_login_at ? dateTime(s.last_login_at) : 'Never'], ['Orders placed (all time)', s.activity.orders_created ?? 0],
                  ['Visits (all time)', s.activity.visits ?? 0]]} />
              </Card>
              <div className="lg:col-span-2">
                <Card title="Recent sync failures" padded={false}>
                  <DataTable rows={s.sync_failures} rowKey={(f) => f.id} empty="No sync failures" columns={[
                    { header: 'When', cell: (f) => dateTime(f.at) },
                    { header: 'Device order', cell: (f) => <span className="font-mono text-xs">{f.client_order_id}</span> },
                    { header: 'Why', cell: (f) => f.message },
                  ]} />
                </Card>
              </div>
            </div>
          )}
          {dialog === 'edit' && <UserForm user={s} onClose={() => setDialog(null)} onSaved={() => done('Salesman saved')} />}
          {dialog === 'status' && (
            <ConfirmDialog title={s.is_active ? 'Deactivate salesman?' : 'Activate salesman?'} danger={s.is_active}
              confirmLabel={s.is_active ? 'Deactivate' : 'Activate'} onClose={() => setDialog(null)}
              message={s.is_active ? `${s.name} is signed out and cannot log in. Retailers must be reassigned first.` : `${s.name} can log in again.`}
              onConfirm={async () => { await admin.updateUser(token, s.id, { is_active: !s.is_active }); done(s.is_active ? 'Salesman deactivated' : 'Salesman activated') }} />
          )}
        </AdminPage>
      )}
    </Loaded>
  )
}

/** Dedicated assignment screen: pick a salesman, see their shops, add / remove / move shops. */
export function AssignmentsPage() {
  const token = useToken()
  const salesmen = useLoad((t, s) => admin.salesmen(t, s), 'assign-salesmen')
  const [salesmanId, setSalesmanId] = useState(new URLSearchParams(window.location.search).get('salesman') ?? '')
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState('none')
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [confirm, setConfirm] = useState<'add' | 'remove' | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const [version, setVersion] = useState(0)
  const action = useAction()
  const onSearch = useCallback((v: string) => setSearch(v), [])
  const assigned = useLoad((t, s) => (salesmanId ? admin.retailers(t, { salesman_id: salesmanId, limit: 100 }, s) : Promise.resolve({ success: true, message: '', data: { items: [], total: 0, page: 1, limit: 100 } })), `assigned|${salesmanId}|${version}`)
  const pool = useLoad((t, s) => admin.retailers(t, { search, salesman_id: scope === 'all' ? '' : scope, status: 'active', limit: 50 }, s), `pool|${search}|${scope}|${version}`)
  const active = salesmen.state.status === 'ready' ? salesmen.state.data.filter((u) => u.is_active) : []
  const current = active.find((u) => u.id === salesmanId)
  const toggle = (id: string) => setChosen((c) => { const n = new Set(c); if (n.has(id)) n.delete(id); else n.add(id); return n })

  async function apply(target: string | null, ids: string[], text: string) {
    if (await action.run(() => admin.assign(token, { salesman_id: target, retailer_ids: ids }))) {
      setChosen(new Set()); setVersion((v) => v + 1); setFlash({ tone: 'success', text })
    }
  }

  return (
    <AdminPage title="Salesman–retailer assignment" subtitle="Each retailer has one salesman. Adding a shop that belongs to someone else moves it.">
      <Flash message={flash} onClose={() => setFlash(null)} />
      {action.error && <ErrorBox message={action.error} />}
      <FilterBar>
        <Select label="Salesman" value={salesmanId} onChange={(v) => { setSalesmanId(v); setChosen(new Set()) }} className="sm:min-w-[260px]"
          options={[['', 'Choose a salesman…'], ...active.map((u) => [u.id, `${u.name} (${u.assigned_retailers} shops)`] as [string, string])]} />
      </FilterBar>
      {current && (
        <div className="grid gap-5 xl:grid-cols-2">
          <Card title={`${current.name}’s retailers`}>
            <Loaded state={assigned.state} reload={assigned.reload}>
              {(d) => d.items.length === 0 ? <p className="text-sm text-ink-soft">No retailers assigned yet.</p> : (
                <ul className="divide-y divide-gray-100">
                  {d.items.map((r) => (
                    <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <span><span className="font-semibold text-ink">{r.shop_name}</span><span className="block text-xs text-ink-soft">{r.city} · {r.phone}</span></span>
                      <Button variant="danger" className="min-h-9 px-3" onClick={() => apply(null, [r.id], `${r.shop_name} is no longer assigned`)}>Remove</Button>
                    </li>
                  ))}
                </ul>
              )}
            </Loaded>
          </Card>
          <Card title="Add retailers" actions={chosen.size > 0 && <Button busy={action.busy} onClick={() => setConfirm('add')}>Assign {chosen.size} to {current.name}</Button>}>
            <div className="flex flex-col gap-2 sm:flex-row">
              <SearchBox value={search} onChange={onSearch} placeholder="Search shop, owner, mobile" />
              <Select label="Show" value={scope} onChange={setScope} options={[['none', 'Not assigned'], ['all', 'All active retailers'],
                ...active.filter((u) => u.id !== current.id).map((u) => [u.id, `${u.name}’s shops`] as [string, string])]} />
            </div>
            <Loaded state={pool.state} reload={pool.reload}>
              {(d) => (
                <ul className="mt-3 max-h-[420px] divide-y divide-gray-100 overflow-y-auto">
                  {d.items.filter((r) => r.salesman?.id !== current.id).map((r) => (
                    <li key={r.id} className="py-2">
                      <Checkbox checked={chosen.has(r.id)} onChange={() => toggle(r.id)}>
                        <span>{r.shop_name} <span className="font-normal text-ink-soft">· {r.city}{r.salesman ? ` · now with ${r.salesman.name}` : ' · not assigned'}</span></span>
                      </Checkbox>
                    </li>
                  ))}
                  {d.items.filter((r) => r.salesman?.id !== current.id).length === 0 && <li className="py-4 text-sm text-ink-soft">No retailers found.</li>}
                </ul>
              )}
            </Loaded>
          </Card>
        </div>
      )}
      {confirm === 'add' && current && pool.state.status === 'ready' && (() => {
        const moving = pool.state.data.items.filter((r) => chosen.has(r.id) && r.salesman)
        return (
          <ConfirmDialog title={`Assign ${chosen.size} retailer(s) to ${current.name}?`} confirmLabel="Assign" onClose={() => setConfirm(null)}
            message={moving.length ? `${moving.length} of them move from their current salesman (${[...new Set(moving.map((r) => r.salesman!.name))].join(', ')}), who will no longer see them.` : 'They will appear in the salesman’s app after the next sync.'}
            onConfirm={() => apply(current.id, [...chosen], `${chosen.size} retailer(s) assigned to ${current.name}`)} />
        )
      })()}
    </AdminPage>
  )
}
