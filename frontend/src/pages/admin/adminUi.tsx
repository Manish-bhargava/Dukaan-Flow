import { useEffect, useState, type ReactNode } from 'react'
import { useAction } from './adminHooks'
import { Icon, type IconName } from '../../components/Icon'
import { Button, Empty, ErrorBox, Loading } from '../../components/ui'

/** Admin building blocks: page frame, cards, tables, filters, forms, dialogs, messages. */

export function AdminPage({ title, subtitle, actions, back, children }: {
  title: string; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode; children: ReactNode
}) {
  return (
    <div>
      {back && <div className="mb-2 text-sm font-bold text-leaf-700 print:hidden">{back}</div>}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold text-ink sm:text-2xl">{title}</h1>
          {subtitle && <div className="mt-0.5 text-sm text-ink-soft">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      <div className="mt-5 space-y-5">{children}</div>
    </div>
  )
}

export function Card({ title, actions, children, padded = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; padded?: boolean }) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white">
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-4 py-3">
          {title && <h2 className="font-extrabold text-ink">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={padded ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, icon, tone = 'plain' }: { label: string; value: ReactNode; hint?: ReactNode; icon: IconName; tone?: 'plain' | 'warn' | 'good' | 'bad' }) {
  const tones = { plain: 'bg-leaf-50 text-leaf-700', warn: 'bg-mango-100 text-mango-600', good: 'bg-leaf-100 text-leaf-800', bad: 'bg-red-50 text-red-700' }[tone]
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-gray-200 bg-white p-4">
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tones}`}><Icon name={icon} /></span>
      <span className="min-w-0">
        <span className="block text-xl font-extrabold leading-tight text-ink">{value}</span>
        <span className="block text-sm font-semibold text-ink">{label}</span>
        {hint && <span className="block text-xs text-ink-soft">{hint}</span>}
      </span>
    </div>
  )
}

export function Pill({ tone, children }: { tone: 'green' | 'gray' | 'amber' | 'red' | 'blue'; children: ReactNode }) {
  const styles = {
    green: 'bg-leaf-50 text-leaf-700', gray: 'bg-gray-100 text-gray-600', amber: 'bg-mango-100 text-mango-600',
    red: 'bg-red-50 text-red-700', blue: 'bg-sky-50 text-sky-800',
  }[tone]
  return <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-bold ${styles}`}>{children}</span>
}

export const ActivePill = ({ active }: { active: boolean }) => <Pill tone={active ? 'green' : 'gray'}>{active ? 'Active' : 'Inactive'}</Pill>

export function KeyValues({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="space-y-2 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4">
          <dt className="shrink-0 text-ink-soft">{k}</dt>
          <dd className="min-w-0 break-words text-right font-semibold text-ink">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Tabs<T extends string>({ value, onChange, tabs }: { value: T; onChange: (v: T) => void; tabs: [T, string][] }) {
  return (
    <div className="-mx-1 flex overflow-x-auto border-b border-gray-200" role="tablist">
      {tabs.map(([id, label]) => (
        <button key={id} type="button" role="tab" aria-selected={value === id} onClick={() => onChange(id)}
          className={`min-h-11 shrink-0 border-b-2 px-3 text-sm font-bold ${value === id ? 'border-leaf-700 text-leaf-800' : 'border-transparent text-ink-soft hover:text-leaf-700'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- tables

export interface Column<T> {
  header: string
  cell: (row: T) => ReactNode
  align?: 'right'
  /** Hidden in the phone card view. */
  wide?: boolean
}

export function DataTable<T>({ rows, columns, rowKey, onRow, empty = 'Nothing to show', loading = false }: {
  rows: T[]; columns: Column<T>[]; rowKey: (row: T) => string; onRow?: (row: T) => void; empty?: string; loading?: boolean
}) {
  if (rows.length === 0) return <Empty title={empty} />
  const [first, ...rest] = columns
  return (
    <div className={loading ? 'opacity-60' : ''}>
      <div className="hidden overflow-x-auto rounded-2xl border border-gray-200 bg-white md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-ink-soft">
            <tr>{columns.map((c) => <th key={c.header} className={`whitespace-nowrap px-3 py-2.5 first:pl-4 ${c.align === 'right' ? 'text-right' : ''}`}>{c.header}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((r) => (
              <tr key={rowKey(r)} onClick={onRow ? () => onRow(r) : undefined}
                className={`align-top ${onRow ? 'cursor-pointer hover:bg-leaf-50/40' : ''}`}>
                {columns.map((c) => <td key={c.header} className={`px-3 py-3 first:pl-4 ${c.align === 'right' ? 'text-right' : ''}`}>{c.cell(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-2 md:hidden">
        {rows.map((r) => (
          <li key={rowKey(r)} onClick={onRow ? () => onRow(r) : undefined}
            className={`rounded-2xl border border-gray-200 bg-white p-3 text-sm ${onRow ? 'cursor-pointer active:bg-gray-50' : ''}`}>
            <div className="font-semibold text-ink">{first.cell(r)}</div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
              {rest.filter((c) => !c.wide).map((c) => (
                <div key={c.header} className="min-w-0">
                  <dt className="text-[11px] font-bold uppercase text-gray-400">{c.header}</dt>
                  <dd className="min-w-0 break-words text-ink">{c.cell(r)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Loading / error / content for a useLoad result. */
export function Loaded<T>({ state, reload, children, label }: {
  state: { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T }
  reload: () => void; children: (data: T) => ReactNode; label?: string
}) {
  if (state.status === 'error') return <ErrorBox message={state.message} onRetry={reload} />
  if (state.status === 'loading') return <Loading label={label} />
  return <>{children(state.data)}</>
}

// ---------------------------------------------------------------- filters and forms

const input = 'min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm text-ink outline-none focus:border-leaf-600 disabled:bg-gray-50'

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-2 rounded-2xl border border-gray-200 bg-white p-3 sm:flex-row sm:flex-wrap sm:items-end">{children}</div>
}

export function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const [text, setText] = useState(value)
  useEffect(() => {
    if (text.trim() === value) return
    const timer = window.setTimeout(() => onChange(text.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [text, value, onChange])
  return (
    <div className="relative min-w-0 flex-1 sm:min-w-[240px]">
      <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-soft" />
      <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder}
        className={`${input} pl-10`} />
    </div>
  )
}

export function Select({ label, value, onChange, options, className = '' }: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][]; className?: string
}) {
  return (
    <label className={`block text-xs font-bold text-ink-soft ${className}`}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${input} mt-1`}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <label className="block text-xs font-bold text-ink-soft">
      {label}
      <div className="mt-1">{children}</div>
      {hint && !error && <span className="mt-1 block font-normal">{hint}</span>}
      {error && <span className="mt-1 block font-semibold text-red-700">{error}</span>}
    </label>
  )
}

export function TextInput({ value, onChange, type = 'text', ...rest }: {
  value: string; onChange: (v: string) => void; type?: string; placeholder?: string; inputMode?: 'numeric' | 'decimal' | 'tel' | 'email'
  maxLength?: number; disabled?: boolean; required?: boolean; min?: string; step?: string
}) {
  return <input type={type} value={value} onChange={(e) => onChange(e.target.value)} className={input} {...rest} />
}

export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex items-center gap-2 text-sm font-semibold text-ink">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-leaf-700" />
      {children}
    </label>
  )
}

// ---------------------------------------------------------------- dialogs and messages

export function Modal({ title, onClose, children, footer, wide = false }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl ${wide ? 'sm:max-w-2xl' : 'sm:max-w-md'}`}>
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-gray-100 bg-white px-5 py-3">
          <h2 className="text-lg font-extrabold text-ink">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="flex h-10 w-10 items-center justify-center rounded-lg text-ink-soft hover:bg-gray-100">
            <Icon name="xCircle" />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">{children}</div>
        {footer && <div className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-gray-100 bg-white px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, message, confirmLabel, danger = false, onConfirm, onClose, children }: {
  title: string; message: ReactNode; confirmLabel: string; danger?: boolean; onConfirm: () => Promise<unknown>; onClose: () => void; children?: ReactNode
}) {
  const action = useAction()
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button variant={danger ? 'danger' : 'primary'} busy={action.busy} onClick={async () => {
        if (await action.run(onConfirm)) onClose()
      }}>{confirmLabel}</Button>
    </>}>
      <div className="text-sm text-ink">{message}</div>
      {children}
      {action.error && <ErrorBox message={action.error} />}
    </Modal>
  )
}

export function Flash({ message, onClose }: { message: { tone: 'success' | 'error'; text: string } | null; onClose: () => void }) {
  useEffect(() => {
    if (!message || message.tone === 'error') return
    const t = window.setTimeout(onClose, 4000)
    return () => window.clearTimeout(t)
  }, [message, onClose])
  if (!message) return null
  return (
    <div role="status" className={`flex items-start justify-between gap-3 rounded-xl border p-3 text-sm font-semibold ${
      message.tone === 'success' ? 'border-leaf-200 bg-leaf-50 text-leaf-800' : 'border-red-200 bg-red-50 text-red-800'}`}>
      <span>{message.text}</span>
      <button type="button" onClick={onClose} className="shrink-0 text-xs underline">Dismiss</button>
    </div>
  )
}

export type FlashMessage = { tone: 'success' | 'error'; text: string } | null
