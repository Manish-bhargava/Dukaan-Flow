import { useCallback, useState } from 'react'
import { admin, type AdminUser, type Role } from '../../api/admin'
import { ROLE_LABELS } from '../../api/auth'
import { useAuth } from '../../auth/AuthContext'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox, Notice } from '../../components/ui'
import { dateTime } from '../../format'
import { Pager } from '../desk/deskUi'
import { ACTION_LABELS, describeChange } from './adminFormat'
import {
  ActivePill, AdminPage, ConfirmDialog, DataTable, Field, FilterBar, Flash, KeyValues, Loaded, Modal, SearchBox, Select, TextInput,
  type FlashMessage,
} from './adminUi'
import { useAction } from './adminHooks'

const LIMIT = 20
const STAFF: [string, string][] = [['SALESMAN', 'Salesman'], ['ORDER_DESK', 'Order Desk'], ['ADMIN', 'Admin']]

/** Create or edit a staff account (salesman, order desk, admin). Retailer logins are managed with their retailer. */
export function UserForm({ user, role, onClose, onSaved }: { user?: AdminUser; role?: Role; onClose: () => void; onSaved: (u: AdminUser) => void }) {
  const token = useToken()
  const action = useAction()
  const { state } = useAuth()
  const self = state.status === 'authenticated' && state.user.id === user?.id
  const [f, setF] = useState({ name: user?.name ?? '', phone: user?.phone ?? '', email: user?.email ?? '', role: user?.role ?? role ?? 'SALESMAN', password: '' })
  const set = (k: keyof typeof f) => (v: string) => setF({ ...f, [k]: v })
  const retailer = user?.role === 'RETAILER'
  const valid = f.name.trim() && /^[6-9]\d{9}$/.test(f.phone) && (user || f.password.length >= 8)

  async function save() {
    let saved: AdminUser | undefined
    const body = user
      ? { name: f.name.trim(), phone: f.phone, email: f.email.trim() || null, ...(retailer || self || f.role === user.role ? {} : { role: f.role }) }
      : { name: f.name.trim(), phone: f.phone, email: f.email.trim() || null, role: f.role, password: f.password }
    const ok = await action.run(async () => {
      saved = (await (user ? admin.updateUser(token, user.id, body) : admin.createUser(token, body))).data
    })
    if (ok && saved) onSaved(saved)
  }

  return (
    <Modal title={user ? `Edit ${user.name}` : `Add ${ROLE_LABELS[f.role as Role].toLowerCase()}`} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!valid} onClick={save}>{user ? 'Save' : 'Create account'}</Button>
    </>}>
      <Field label="Name"><TextInput value={f.name} onChange={set('name')} maxLength={150} /></Field>
      <Field label="Mobile (login)"><TextInput value={f.phone} onChange={(v) => set('phone')(v.replace(/\D/g, '').slice(0, 10))} inputMode="tel" /></Field>
      <Field label="Email (optional)"><TextInput value={f.email} onChange={set('email')} type="email" maxLength={255} /></Field>
      {!retailer && <Select label="Role" value={f.role} onChange={set('role')} options={STAFF} />}
      {self && <p className="text-xs text-ink-soft">You cannot change your own role.</p>}
      {user && !retailer && f.role !== user.role && <Notice tone="warn">Changing the role signs {user.name} out; they log in again with the new role.</Notice>}
      {!user && <Field label="Password" hint="At least 8 characters. Share it with the user privately."><TextInput value={f.password} onChange={set('password')} type="password" /></Field>}
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

function PasswordDialog({ user, onClose, onSaved }: { user: AdminUser; onClose: () => void; onSaved: () => void }) {
  const token = useToken()
  const action = useAction()
  const [password, setPassword] = useState('')
  return (
    <Modal title={`Reset password: ${user.name}`} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={password.length < 8} onClick={async () => { if (await action.run(() => admin.resetPassword(token, user.id, password))) onSaved() }}>Set password</Button>
    </>}>
      <Field label="New password" hint="At least 8 characters. It is stored hashed and never shown again."><TextInput value={password} onChange={setPassword} type="password" /></Field>
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

function UserActivity({ user, onClose }: { user: AdminUser; onClose: () => void }) {
  const detail = useLoad((t, s) => admin.user(t, user.id, s), `user-${user.id}`)
  return (
    <Modal title={user.name} onClose={onClose} wide>
      <Loaded state={detail.state} reload={detail.reload}>
        {(d) => (
          <>
            <KeyValues rows={[['Role', ROLE_LABELS[d.role]], ['Mobile', d.phone], ['Email', d.email ?? '—'], ['Status', <ActivePill key="s" active={d.is_active} />],
              ['Last login', d.last_login_at ? dateTime(d.last_login_at) : 'Never'], ['Account created', dateTime(d.created_at)],
              ['Orders placed', d.activity.orders_created], ['Order desk actions', d.activity.order_actions], ['Visits', d.activity.visits], ['Admin changes', d.activity.admin_changes]]} />
            <h3 className="font-extrabold text-ink">Recent actions</h3>
            {d.recent.length === 0 ? <p className="text-sm text-ink-soft">No recorded actions.</p> : (
              <ul className="space-y-2 text-sm">
                {d.recent.map((e) => (
                  <li key={e.id}><b>{ACTION_LABELS[e.action] ?? e.action}</b> · {e.label} <span className="text-xs text-ink-soft">{dateTime(e.at)}</span><span className="block text-xs text-ink-soft">{describeChange(e)}</span></li>
                ))}
              </ul>
            )}
            {d.retailer && <Link to={`/admin/retailers/${d.retailer.id}`} className="text-sm font-bold text-leaf-700">Open {d.retailer.shop_name} →</Link>}
          </>
        )}
      </Loaded>
    </Modal>
  )
}

export function UsersPage() {
  const token = useToken()
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [version, setVersion] = useState(0)
  const [dialog, setDialog] = useState<{ kind: 'new' | 'edit' | 'password' | 'status' | 'view'; user?: AdminUser } | null>(null)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const onSearch = useCallback((v: string) => { setSearch(v); setPage(1) }, [])
  const list = useLoad((t, s) => admin.users(t, { role, status, search, page, limit: LIMIT }, s), `${role}|${status}|${search}|${page}|${version}`)
  const done = (text: string) => { setDialog(null); setFlash({ tone: 'success', text }); setVersion((v) => v + 1) }
  const u = dialog?.user

  return (
    <AdminPage title="Users & roles" subtitle="Everyone who can sign in. Staff use a password; retailers use a one-time code sent to their email."
      actions={<Button onClick={() => setDialog({ kind: 'new' })}>+ Add staff user</Button>}>
      <Flash message={flash} onClose={() => setFlash(null)} />
      <FilterBar>
        <SearchBox value={search} onChange={onSearch} placeholder="Search name, mobile or email" />
        <Select label="Role" value={role} onChange={(v) => { setRole(v); setPage(1) }} options={[['', 'All roles'], ['ADMIN', 'Admin'], ['ORDER_DESK', 'Order Desk'], ['SALESMAN', 'Salesman'], ['RETAILER', 'Retailer']]} />
        <Select label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={[['', 'All'], ['active', 'Active'], ['inactive', 'Inactive']]} />
      </FilterBar>
      <Loaded state={list.state} reload={list.reload}>
        {(d) => (
          <>
            <DataTable rows={d.items} rowKey={(r) => r.id} loading={list.loading} empty="No users match" columns={[
              { header: 'User', cell: (r) => <button type="button" onClick={() => setDialog({ kind: 'view', user: r })} className="text-left"><span className="font-semibold text-ink hover:text-leaf-700">{r.name}</span><span className="block text-xs text-ink-soft">{r.phone}{r.email ? ` · ${r.email}` : ''}</span></button> },
              { header: 'Role', cell: (r) => <>{ROLE_LABELS[r.role]}{r.retailer && <span className="block text-xs text-ink-soft">{r.retailer.shop_name}</span>}</> },
              { header: 'Last login', cell: (r) => (r.last_login_at ? dateTime(r.last_login_at) : 'Never') },
              { header: 'Status', cell: (r) => <ActivePill active={r.is_active} /> },
              { header: '', cell: (r) => (
                <span className="flex flex-wrap gap-3">
                  <button type="button" className="font-bold text-leaf-700 underline" onClick={() => setDialog({ kind: 'edit', user: r })}>Edit</button>
                  {r.role !== 'RETAILER' && <button type="button" className="font-bold text-ink-soft underline" onClick={() => setDialog({ kind: 'password', user: r })}>Reset password</button>}
                  <button type="button" className="font-bold text-ink-soft underline" onClick={() => setDialog({ kind: 'status', user: r })}>{r.is_active ? 'Deactivate' : 'Activate'}</button>
                </span>
              ) },
            ]} />
            <Pager page={page} total={d.total} limit={LIMIT} onPage={setPage} />
          </>
        )}
      </Loaded>
      {dialog?.kind === 'new' && <UserForm onClose={() => setDialog(null)} onSaved={(x) => done(`${x.name} added`)} />}
      {dialog?.kind === 'edit' && u && <UserForm user={u} onClose={() => setDialog(null)} onSaved={(x) => done(`${x.name} saved`)} />}
      {dialog?.kind === 'password' && u && <PasswordDialog user={u} onClose={() => setDialog(null)} onSaved={() => done(`Password reset for ${u.name}`)} />}
      {dialog?.kind === 'view' && u && <UserActivity user={u} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'status' && u && (
        <ConfirmDialog title={u.is_active ? `Deactivate ${u.name}?` : `Activate ${u.name}?`} danger={u.is_active}
          confirmLabel={u.is_active ? 'Deactivate' : 'Activate'} onClose={() => setDialog(null)}
          message={u.is_active ? 'They are signed out at once and cannot log in until activated again.' : 'They can log in again.'}
          onConfirm={async () => { await admin.updateUser(token, u.id, { is_active: !u.is_active }); done(u.is_active ? `${u.name} deactivated` : `${u.name} activated`) }} />
      )}
    </AdminPage>
  )
}
