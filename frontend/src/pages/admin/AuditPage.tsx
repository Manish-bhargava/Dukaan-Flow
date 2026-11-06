import { useCallback, useState } from 'react'
import { admin } from '../../api/admin'
import { ROLE_LABELS } from '../../api/auth'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { dateTime } from '../../format'
import { Pager } from '../desk/deskUi'
import { ACTION_LABELS, describeChange, ENTITY_LABELS } from './adminFormat'
import { AdminPage, DataTable, Field, FilterBar, Loaded, SearchBox, Select, TextInput } from './adminUi'

const LIMIT = 50

function entityLink(type: string, id: string | null): string | null {
  if (!id) return null
  if (type === 'order') return `/desk/orders/${id}`
  if (type === 'retailer' || type === 'credit') return `/admin/retailers/${id}`
  if (type === 'product' || type === 'price' || type === 'stock') return `/admin/products/${id}`
  return null
}

/** Who did what: master-data changes and order actions, newest first. */
export function AuditPage() {
  const [source, setSource] = useState(() => new URLSearchParams(window.location.search).get('source') ?? 'all')
  const [entity, setEntity] = useState('')
  const [search, setSearch] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const log = useLoad((t, s) => admin.audit(t, { source, entity_type: entity, search, from_date: from, to_date: to, page, limit: LIMIT }, s),
    `${source}|${entity}|${search}|${from}|${to}|${page}`)
  const reset = (set: (v: string) => void) => (v: string) => { set(v); setPage(1) }

  return (
    <AdminPage title="Audit log" subtitle="Every recorded change: who, what, when and the details. Entries cannot be edited or deleted.">
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search by name, order number…" />
        <Select label="Source" value={source} onChange={reset(setSource)} options={[['all', 'Everything'], ['master', 'Master data'], ['orders', 'Orders']]} />
        <Select label="Area" value={entity} onChange={reset(setEntity)} options={[['', 'All'], ...Object.entries(ENTITY_LABELS)]} />
        <Field label="From"><TextInput type="date" value={from} onChange={reset(setFrom)} /></Field>
        <Field label="To"><TextInput type="date" value={to} onChange={reset(setTo)} /></Field>
      </FilterBar>
      <Loaded state={log.state} reload={log.reload}>
        {(d) => (
          <>
            <DataTable rows={d.items} rowKey={(e) => e.id} loading={log.loading} empty="Nothing recorded for these filters" columns={[
              { header: 'When', cell: (e) => dateTime(e.at) },
              { header: 'User', cell: (e) => (e.actor ? <>{e.actor.name}<span className="block text-xs text-ink-soft">{ROLE_LABELS[e.actor.role]}</span></> : <span className="text-ink-soft">Not recorded</span>) },
              { header: 'Action', cell: (e) => <span className="font-semibold text-ink">{ACTION_LABELS[e.action] ?? e.action}</span> },
              { header: 'Entity', cell: (e) => {
                const href = entityLink(e.entity_type, e.entity_id)
                const text = `${ENTITY_LABELS[e.entity_type] ?? e.entity_type}: ${e.label ?? '—'}`
                return href ? <Link to={href} className="text-leaf-700">{text}</Link> : text
              } },
              { header: 'Details', cell: (e) => <span className="text-ink-soft">{[e.message, describeChange(e)].filter((x, i, a) => x && a.indexOf(x) === i).join(' · ') || '—'}</span>, wide: true },
            ]} />
            <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </Loaded>
    </AdminPage>
  )
}
