import { useState } from 'react'
import { admin, type Settings } from '../../api/admin'
import { useLoad, useToken } from '../../auth/useApi'
import { Button, ErrorBox } from '../../components/ui'
import { AdminPage, Card, Field, Flash, Loaded, TextInput, type FlashMessage } from './adminUi'
import { useAction } from './adminHooks'

/** Business settings the application actually uses. */
export function SettingsPage() {
  const data = useLoad((t, s) => admin.settings(t, s), 'admin-settings')
  return (
    <Loaded state={data.state} reload={data.reload}>
      {(s) => <SettingsForm initial={s} onSaved={data.setData} />}
    </Loaded>
  )
}

function SettingsForm({ initial, onSaved }: { initial: Settings; onSaved: (s: Settings) => void }) {
  const token = useToken()
  const action = useAction()
  const [f, setF] = useState(initial)
  const [flash, setFlash] = useState<FlashMessage>(null)
  const text = (k: keyof Settings) => (v: string) => setF({ ...f, [k]: v })
  const num = (k: keyof Settings) => (v: string) => setF({ ...f, [k]: v === '' ? ('' as unknown as number) : Number(v.replace(/\D/g, '')) })
  const changed = JSON.stringify(f) !== JSON.stringify(initial)
  const valid = f.business_name.trim() && [f.low_stock_cases, f.inactive_retailer_days, f.duplicate_window_hours, f.ai_low_confidence_percent].every((n) => typeof n === 'number')

  async function save() {
    let saved: Settings | undefined
    if (await action.run(async () => { saved = (await admin.saveSettings(token, f)).data })) {
      onSaved(saved!)
      setFlash({ tone: 'success', text: 'Settings saved' })
    }
  }

  return (
    <AdminPage title="Settings" subtitle="Only settings the application uses. Changes are recorded in the audit log."
      actions={<Button busy={action.busy} disabled={!changed || !valid} onClick={save}>Save settings</Button>}>
      <Flash message={flash} onClose={() => setFlash(null)} />
      {action.error && <ErrorBox message={action.error} />}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Business information">
          <div className="space-y-3">
            <Field label="Business name" hint="Shown on the admin dashboard"><TextInput value={f.business_name} onChange={text('business_name')} maxLength={150} /></Field>
            <Field label="Address"><TextInput value={f.business_address} onChange={text('business_address')} maxLength={300} /></Field>
            <Field label="Phone"><TextInput value={f.business_phone} onChange={text('business_phone')} maxLength={20} /></Field>
            <Field label="GSTIN"><TextInput value={f.business_gstin} onChange={(v) => text('business_gstin')(v.toUpperCase())} maxLength={20} /></Field>
          </div>
        </Card>
        <Card title="Stock & retailers">
          <div className="space-y-3">
            <Field label="Low-stock level (cases)" hint="Products at or below this are “low stock” on the dashboard, stock page and reports">
              <TextInput value={String(f.low_stock_cases)} onChange={num('low_stock_cases')} inputMode="numeric" />
            </Field>
            <Field label="“Not ordered recently” after (days)" hint="Retailers without an order for this long are flagged">
              <TextInput value={String(f.inactive_retailer_days)} onChange={num('inactive_retailer_days')} inputMode="numeric" />
            </Field>
          </div>
        </Card>
        <Card title="Order desk checks">
          <div className="space-y-3">
            <Field label="Possible duplicate window (hours)" hint="Same shop, same items within this time is flagged as a possible duplicate">
              <TextInput value={String(f.duplicate_window_hours)} onChange={num('duplicate_window_hours')} inputMode="numeric" />
            </Field>
            <Field label="AI match warning below (%)" hint="AI lines matched with less confidence are flagged for the order desk">
              <TextInput value={String(f.ai_low_confidence_percent)} onChange={num('ai_low_confidence_percent')} inputMode="numeric" />
            </Field>
          </div>
        </Card>
        <Card title="Rules enforced by the system">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
            <li>Retailers cannot order above their available credit; salesman orders above it wait on credit hold.</li>
            <li>Schemes are never combined: one active scheme per product at a time.</li>
            <li>Every order (retailer app, salesman app, AI) waits for the order desk to accept or reject it; stock and credit change only on acceptance.</li>
            <li>Login codes are emailed to retailers; there are no SMS or notification settings in this version.</li>
          </ul>
        </Card>
      </div>
    </AdminPage>
  )
}
