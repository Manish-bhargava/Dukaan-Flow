import type { ReactNode } from 'react'
import { Icon, type IconName } from '../components/Icon'
import { Link } from '../components/Link'

/** Shared building blocks for the salesman app (iOS-style grouped layout). */

export { Icon, type IconName } from '../components/Icon'

/** A screen: optional back button, large title, optional subtitle and trailing action. */
export function Screen({ title, subtitle, back, action, children }: {
  title: string; subtitle?: ReactNode; back?: { to: string; label: string }; action?: ReactNode; children: ReactNode
}) {
  return (
    <div className="space-y-5">
      <header>
        {back && (
          <Link to={back.to} className="-ml-1 mb-1 inline-flex min-h-10 items-center gap-0.5 text-[15px] font-semibold text-leaf-700">
            <Icon name="chevronLeft" className="h-5 w-5" /> {back.label}
          </Link>
        )}
        <div className="flex items-end justify-between gap-3">
          <h1 className="text-[28px] font-extrabold leading-tight tracking-tight text-ink">{title}</h1>
          {action}
        </div>
        {subtitle && <p className="mt-1 text-[15px] text-ink-soft">{subtitle}</p>}
      </header>
      {children}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/5 ${className}`}>{children}</div>
}

/** Section label above a group (iOS grouped list style). */
export function SectionLabel({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-center justify-between px-1">
      <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-soft">{children}</h2>
      {action}
    </div>
  )
}

export function ListGroup({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-gray-100 overflow-hidden rounded-2xl bg-white shadow-[0_1px_2px_rgba(16,24,40,0.05)] ring-1 ring-black/5">{children}</ul>
}

/** A tappable list row with optional leading icon/content and trailing content + chevron. */
export function ListRow({ to, href, onClick, leading, title, subtitle, trailing, chevron = Boolean(to || onClick) }: {
  to?: string; href?: string; onClick?: () => void; leading?: ReactNode; title: ReactNode; subtitle?: ReactNode; trailing?: ReactNode; chevron?: boolean
}) {
  const body = (
    <div className="flex min-h-14 items-center gap-3 px-4 py-3">
      {leading}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[16px] font-semibold text-ink">{title}</div>
        {subtitle && <div className="mt-0.5 text-[13px] leading-snug text-ink-soft">{subtitle}</div>}
      </div>
      {trailing && <div className="shrink-0 text-right">{trailing}</div>}
      {chevron && <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-gray-300" />}
    </div>
  )
  if (to) return <li><Link to={to} className="block active:bg-gray-50">{body}</Link></li>
  if (href) return <li><a href={href} className="block active:bg-gray-50">{body}</a></li>
  if (onClick) return <li><button type="button" onClick={onClick} className="block w-full text-left active:bg-gray-50">{body}</button></li>
  return <li>{body}</li>
}

/** Rounded square icon tile used as a list row's leading element. */
export function IconTile({ name, tone = 'leaf' }: { name: IconName; tone?: 'leaf' | 'mango' | 'gray' | 'red' }) {
  const styles = { leaf: 'bg-leaf-50 text-leaf-700', mango: 'bg-mango-100 text-mango-600', gray: 'bg-gray-100 text-ink-soft', red: 'bg-red-50 text-red-700' }[tone]
  return <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${styles}`}><Icon name={name} className="h-[18px] w-[18px]" /></span>
}

/** Initials avatar for a shop or person. */
export function Avatar({ name, size = 'h-11 w-11 text-base' }: { name: string; size?: string }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')
  return <span className={`flex shrink-0 items-center justify-center rounded-full bg-leaf-100 font-bold text-leaf-800 ${size}`} aria-hidden="true">{initials}</span>
}

export function PrimaryButton({ children, onClick, disabled, busy, tone = 'leaf', className = '' }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; busy?: boolean; tone?: 'leaf' | 'mango' | 'danger'; className?: string
}) {
  const styles = {
    leaf: 'bg-leaf-700 text-white active:bg-leaf-800 disabled:bg-leaf-700/40',
    mango: 'bg-mango-400 text-leaf-950 active:bg-mango-300 disabled:opacity-50',
    danger: 'bg-white text-red-700 ring-1 ring-red-200 active:bg-red-50 disabled:opacity-50',
  }[tone]
  return (
    <button type="button" onClick={onClick} disabled={disabled || busy}
      className={`flex min-h-[52px] w-full items-center justify-center gap-2 rounded-2xl px-5 text-[17px] font-semibold transition-colors disabled:cursor-not-allowed ${styles} ${className}`}>
      {busy ? 'Please wait…' : children}
    </button>
  )
}

/** iOS-style segmented control. */
export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="grid rounded-xl bg-gray-200/70 p-0.5" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }} role="tablist">
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={`min-h-9 rounded-[10px] text-[13px] font-semibold transition ${value === o.value ? 'bg-white text-ink shadow-sm' : 'text-ink-soft'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function SearchField({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="flex min-h-11 items-center gap-2 rounded-xl bg-gray-200/60 px-3 text-ink-soft focus-within:ring-2 focus-within:ring-leaf-500">
      <Icon name="search" className="h-[18px] w-[18px]" />
      <span className="sr-only">{placeholder}</span>
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-soft/70" />
    </label>
  )
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl bg-white px-6 py-10 text-center ring-1 ring-black/5">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 text-ink-soft"><Icon name={icon} className="h-6 w-6" /></span>
      <p className="mt-3 text-[16px] font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 text-[14px] text-ink-soft">{children}</div>}
    </div>
  )
}
