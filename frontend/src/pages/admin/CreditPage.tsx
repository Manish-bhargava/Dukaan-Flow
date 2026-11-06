import { useCallback, useState } from 'react'
import { admin, type RetailerRow } from '../../api/admin'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { creditLevel, CREDIT_LEVEL_STYLES, dateTime, rupees } from '../../format'
import { Pager } from '../desk/deskUi'
import { AdminPage, DataTable, FilterBar, Flash, Loaded, Pill, SearchBox, Select, type FlashMessage } from './adminUi'
import { useSalesmanOptions } from './adminHooks'
import { CreditDialog } from './RetailerPages'

const LIMIT = 20

/** Credit limits, outstanding amounts and ordering pauses for all retailers. */
export function CreditPage() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [salesman, setSalesman] = useState('')
  const [page, setPage] = useState(1)
  const [version, setVersion] = useState(0)
  const [editing, setEditing] = useState<RetailerRow | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const salesmen = useSalesmanOptions()
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.retailers(t, { search, status, salesman_id: salesman, sort: 'outstanding', page, limit: LIMIT }, s),
    `${search}|${status}|${salesman}|${page}|${version}`)

  return (
    <AdminPage title="Credit" subtitle="Set credit limits and pause ordering. Credit is checked by the server on every order; history is on each retailer's page.">
      <Flash message={flash} onClose={() => setFlash(null)} />
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search shop, owner or mobile" />
        <Select label="Show" value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={[['', 'All retailers'], ['restricted', 'Ordering paused'], ['active', 'Active'], ['inactive', 'Inactive']]} />
        <Select label="Salesman" value={salesman} onChange={(v) => { setSalesman(v); setPage(1) }} options={salesmen} />
      </FilterBar>
      <Loaded state={list.state} reload={list.reload}>
        {(d) => (
          <>
            <DataTable rows={d.items} rowKey={(r) => r.id} loading={list.loading} empty="No retailers match" columns={[
              { header: 'Retailer', cell: (r) => <Link to={`/admin/retailers/${r.id}`} className="font-semibold text-ink hover:text-leaf-700">{r.shop_name}<span className="block text-xs font-normal text-ink-soft">{r.salesman?.name ?? 'No salesman'}</span></Link> },
              { header: 'Credit limit', align: 'right', cell: (r) => (r.credit_limit ? rupees(r.credit_limit) : '—') },
              { header: 'Outstanding', align: 'right', cell: (r) => (r.outstanding ? rupees(r.outstanding) : '—') },
              { header: 'Limit left', align: 'right', cell: (r) => {
                if (!r.credit_limit || r.outstanding == null) return '—'
                const left = Number(r.credit_limit) - Number(r.outstanding)
                return <span className={CREDIT_LEVEL_STYLES[creditLevel(left, r.credit_limit)].text}>{rupees(left)}</span>
              } },
              { header: 'Last order', cell: (r) => (r.last_order_at ? dateTime(r.last_order_at) : 'Never'), wide: true },
              { header: 'Ordering', cell: (r) => (r.ordering_restricted_reason ? <Pill tone="red">Paused</Pill> : r.is_active ? <Pill tone="green">Allowed</Pill> : <Pill tone="gray">Inactive</Pill>) },
              { header: '', cell: (r) => <button type="button" className="font-bold text-leaf-700 underline" onClick={() => setEditing(r)}>Change</button> },
            ]} />
            <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
            <p className="text-xs text-ink-soft">“Limit left” is limit minus outstanding; the available credit shown to retailers also holds back their orders under review.</p>
          </>
        )}
      </Loaded>
      {editing && <CreditDialog retailer={{ ...editing, credit_limit: editing.credit_limit ?? null }} onClose={() => setEditing(null)}
        onSaved={() => { setFlash({ tone: 'success', text: `Credit saved for ${editing.shop_name}` }); setEditing(null); setVersion((v) => v + 1) }} />}
    </AdminPage>
  )
}
