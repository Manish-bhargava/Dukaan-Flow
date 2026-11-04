import type { ReactNode } from 'react'
import type { OrderSource, OrderStatus } from '../api/orders'
import { SOURCE_LABELS, STATUS_LABELS, STATUS_STYLES } from '../format'
import { Spinner } from './Spinner'

export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-bold ${STATUS_STYLES[status]}`}>{STATUS_LABELS[status]}</span>
}

export function SourceBadge({ source }: { source: OrderSource }) {
  if (source !== 'AI') return <span className="text-xs font-semibold text-ink-soft">{SOURCE_LABELS[source]}</span>
  return <span className="inline-block rounded-full bg-mango-100 px-2 py-0.5 text-xs font-bold text-mango-600">AI text</span>
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-semibold">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-3 min-h-11 rounded-lg bg-white px-4 font-bold text-red-800 ring-1 ring-red-200">
          Try again
        </button>
      )}
    </div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'success' | 'warn' }) {
  const styles = {
    info: 'border-gray-200 bg-gray-50 text-ink',
    success: 'border-leaf-200 bg-leaf-50 text-leaf-800',
    warn: 'border-mango-200 bg-mango-100/60 text-leaf-950',
  }[tone]
  return <div className={`rounded-xl border p-4 text-sm ${styles}`}>{children}</div>
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm font-medium text-ink-soft">
      <Spinner className="h-5 w-5 text-leaf-600" /> {label}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-300 px-6 py-12 text-center">
      <p className="font-bold text-ink">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-soft">{children}</div>}
    </div>
  )
}

type ButtonProps = {
  children: ReactNode
  onClick?: () => void
  type?: 'button' | 'submit'
  variant?: 'primary' | 'secondary' | 'danger'
  busy?: boolean
  disabled?: boolean
  className?: string
}

export function Button({ children, onClick, type = 'button', variant = 'primary', busy, disabled, className = '' }: ButtonProps) {
  const styles = {
    primary: 'bg-leaf-700 text-white hover:bg-leaf-800 disabled:bg-leaf-700/40',
    secondary: 'bg-white text-leaf-800 ring-1 ring-gray-300 hover:bg-gray-50 disabled:opacity-50',
    danger: 'bg-white text-red-700 ring-1 ring-red-200 hover:bg-red-50 disabled:opacity-50',
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={busy || disabled}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-bold transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {busy && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  )
}

/** Large +/- stepper with a typed value, for cases. */
export function QtyStepper({ value, onChange, max, label }: { value: number; onChange: (n: number) => void; max?: number; label: string }) {
  const clamp = (n: number) => Math.max(0, Math.min(max ?? Infinity, Math.floor(n) || 0))
  return (
    <div className="inline-flex items-center rounded-lg ring-1 ring-gray-300" role="group" aria-label={label}>
      <button type="button" aria-label="One less" onClick={() => onChange(clamp(value - 1))} className="h-11 w-11 text-xl font-bold text-leaf-700 hover:bg-gray-50">
        −
      </button>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        aria-label={`${label} quantity`}
        value={value}
        onChange={(e) => onChange(clamp(Number(e.target.value)))}
        className="h-11 w-14 border-x border-gray-300 text-center font-bold text-ink outline-none [appearance:textfield] focus:bg-leaf-50 [&::-webkit-inner-spin-button]:appearance-none"
      />
      <button
        type="button"
        aria-label="One more"
        disabled={max !== undefined && value >= max}
        onClick={() => onChange(clamp(value + 1))}
        className="h-11 w-11 text-xl font-bold text-leaf-700 hover:bg-gray-50 disabled:opacity-30"
      >
        +
      </button>
    </div>
  )
}
