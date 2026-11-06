import { useState } from 'react'
import { admin, type Named } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { Button, ErrorBox } from '../../components/ui'
import { ActivePill, AdminPage, Card, ConfirmDialog, DataTable, Field, Flash, Loaded, Modal, TextInput, type FlashMessage } from './adminUi'
import { useAction } from './adminHooks'

type Kind = 'category' | 'brand'

/** Categories and brands: create, rename, activate/deactivate. */
export function CatalogSetupPage() {
  const categories = useLoad((t, s) => admin.categories(t, s), 'setup-categories')
  const brands = useLoad((t, s) => admin.brands(t, s), 'setup-brands')
  const [flash, setFlash] = useState<FlashMessage>(null)
  const done = (text: string) => { setFlash({ tone: 'success', text }); categories.reload(); brands.reload() }
  return (
    <AdminPage title="Categories & brands" subtitle="Products are grouped by category and brand. Renaming a brand renames it on all its products.">
      <Flash message={flash} onClose={() => setFlash(null)} />
      <div className="grid gap-5 xl:grid-cols-2">
        <Loaded state={categories.state} reload={categories.reload}>{(rows) => <NamedList kind="category" rows={rows} onDone={done} />}</Loaded>
        <Loaded state={brands.state} reload={brands.reload}>{(rows) => <NamedList kind="brand" rows={rows} onDone={done} />}</Loaded>
      </div>
    </AdminPage>
  )
}

function NamedList({ kind, rows, onDone }: { kind: Kind; rows: Named[]; onDone: (text: string) => void }) {
  const token = useToken()
  const [editing, setEditing] = useState<Named | 'new' | null>(null)
  const [toggling, setToggling] = useState<Named | null>(null)
  const label = kind === 'category' ? 'Category' : 'Brand'
  const update = kind === 'category' ? admin.updateCategory : admin.updateBrand
  return (
    <Card title={kind === 'category' ? 'Categories' : 'Brands'} actions={<Button variant="secondary" onClick={() => setEditing('new')}>+ Add {label.toLowerCase()}</Button>} padded={false}>
      <DataTable rows={rows} rowKey={(r) => r.id} empty={`No ${kind === 'category' ? 'categories' : 'brands'}`} columns={[
        { header: label, cell: (r) => <span className="font-semibold text-ink">{r.name}</span> },
        { header: 'Products', align: 'right', cell: (r) => <Link to={`/admin/products`} className="text-leaf-700">{r.products}</Link> },
        { header: 'Status', cell: (r) => <ActivePill active={r.is_active} /> },
        { header: '', cell: (r) => (
          <span className="flex gap-3">
            <button type="button" className="font-bold text-leaf-700 underline" onClick={() => setEditing(r)}>Rename</button>
            <button type="button" className="font-bold text-ink-soft underline" onClick={() => setToggling(r)}>{r.is_active ? 'Deactivate' : 'Activate'}</button>
          </span>
        ) },
      ]} />
      {editing && <NameDialog kind={kind} item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)}
        onSaved={(text) => { setEditing(null); onDone(text) }} />}
      {toggling && (
        <ConfirmDialog title={`${toggling.is_active ? 'Deactivate' : 'Activate'} ${toggling.name}?`} danger={toggling.is_active}
          confirmLabel={toggling.is_active ? 'Deactivate' : 'Activate'} onClose={() => setToggling(null)}
          message={kind === 'category'
            ? (toggling.is_active ? `Its ${toggling.products} products disappear from all catalogues until it is activated again.` : 'Its products return to the catalogues.')
            : (toggling.is_active ? 'It cannot be chosen for products any more; existing products keep it.' : 'It can be chosen for products again.')}
          onConfirm={async () => { await update(token, toggling.id, { is_active: !toggling.is_active }); onDone(`${label} updated`) }} />
      )}
    </Card>
  )
}

function NameDialog({ kind, item, onClose, onSaved }: { kind: Kind; item?: Named; onClose: () => void; onSaved: (text: string) => void }) {
  const token = useToken()
  const action = useAction()
  const [name, setName] = useState(item?.name ?? '')
  const label = kind === 'category' ? 'Category' : 'Brand'
  async function save() {
    const ok = await action.run(() => item
      ? (kind === 'category' ? admin.updateCategory : admin.updateBrand)(token, item.id, { name: name.trim() })
      : (kind === 'category' ? admin.createCategory : admin.createBrand)(token, name.trim()))
    if (ok) onSaved(item ? `${label} renamed` : `${label} added`)
  }
  return (
    <Modal title={item ? `Rename ${label.toLowerCase()}` : `Add ${label.toLowerCase()}`} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button busy={action.busy} disabled={!name.trim() || name.trim() === item?.name} onClick={save}>Save</Button>
    </>}>
      <Field label={`${label} name`}><TextInput value={name} onChange={setName} maxLength={100} /></Field>
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}
