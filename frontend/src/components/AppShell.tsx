import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ROLE_LABELS, type AuthUser } from '../api/auth'
import { navigate, usePathname } from '../router'
import { Icon, type IconName } from './Icon'
import { Link } from './Link'
import { Logo } from './Logo'

/**
 * The one app layout for every signed-in role (retailer, salesman, order desk):
 * header (logo · optional status · account menu), tabs as a row under the header on
 * larger screens and as a bottom bar on phones (more than 5 tabs: a scrollable row on
 * phones too), and full-width content.
 */
export interface NavTab {
  to: string
  label: string
  icon: IconName
  badge?: number
  /** Extra paths that belong to this tab (e.g. detail pages). */
  match?: (pathname: string) => boolean
}

export interface MenuItem {
  label: string
  to?: string
  onClick?: () => void
  trailing?: ReactNode
  danger?: boolean
}

export interface NavGroup {
  title: string
  tabs: NavTab[]
}

export function AppShell({ user, tabs, sidebar, status, banner, menu, hideMobileNav = false, children }: {
  user: AuthUser
  tabs: NavTab[]
  /** Admin layout: grouped navigation in a left sidebar (large screens) instead of tabs. */
  sidebar?: NavGroup[]
  status?: ReactNode
  banner?: ReactNode
  menu: MenuItem[]
  hideMobileNav?: boolean
  children: ReactNode
}) {
  const pathname = usePathname()
  const isActive = (t: NavTab) => pathname === t.to || Boolean(t.match?.(pathname))
  const manyTabs = tabs.length > 5

  if (sidebar) {
    const all = sidebar.flatMap((g) => g.tabs)
    return (
      <div className="min-h-screen bg-gray-50/60">
        <header className="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur print:hidden">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
            <Logo to="/home" />
            <div className="flex items-center gap-2 sm:gap-3">
              {status}
              <AccountMenu user={user} items={menu} />
            </div>
          </div>
          {banner}
          <nav className="flex gap-1 overflow-x-auto px-4 sm:px-6 lg:hidden" aria-label="Main">
            {all.map((t) => (
              <Link key={t.to} to={t.to} aria-current={isActive(t) ? 'page' : undefined}
                className={`flex min-h-11 shrink-0 items-center gap-1.5 border-b-2 px-2.5 text-sm font-semibold ${
                  isActive(t) ? 'border-leaf-700 text-leaf-800' : 'border-transparent text-ink-soft'}`}>
                <Icon name={t.icon} className="h-4 w-4" /> {t.label}
              </Link>
            ))}
          </nav>
        </header>
        <div className="lg:grid lg:grid-cols-[232px_minmax(0,1fr)]">
          <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] overflow-y-auto border-r border-gray-200 bg-white px-3 py-4 lg:block print:hidden" aria-label="Admin sections">
            {sidebar.map((g) => (
              <div key={g.title} className="mb-4">
                <p className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wider text-gray-400">{g.title}</p>
                <ul className="space-y-0.5">
                  {g.tabs.map((t) => (
                    <li key={t.to}>
                      <Link to={t.to} aria-current={isActive(t) ? 'page' : undefined}
                        className={`flex min-h-10 items-center gap-2.5 rounded-lg px-3 text-sm font-semibold transition-colors ${
                          isActive(t) ? 'bg-leaf-50 text-leaf-800' : 'text-ink-soft hover:bg-gray-50 hover:text-leaf-700'}`}>
                        <Icon name={t.icon} className="h-[18px] w-[18px]" />
                        <span className="flex-1">{t.label}</span>
                        {Boolean(t.badge) && <Badge value={t.badge!} />}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </aside>
          <main className="min-w-0 px-4 pb-12 pt-5 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-[1400px]">{children}</div>
          </main>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur print:hidden">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
          <Logo to="/home" />
          <div className="flex items-center gap-2 sm:gap-3">
            {status}
            <AccountMenu user={user} items={menu} />
          </div>
        </div>
        {banner}
        {tabs.length > 1 && (
          <nav className={`mx-auto max-w-7xl gap-1 px-4 sm:px-6 lg:px-8 ${manyTabs ? 'flex overflow-x-auto print:hidden' : 'hidden md:flex'}`} aria-label="Main">
            {tabs.map((t) => (
              <Link key={t.to} to={t.to} aria-current={isActive(t) ? 'page' : undefined}
                className={`flex min-h-12 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-semibold transition-colors ${
                  isActive(t) ? 'border-leaf-700 text-leaf-800' : 'border-transparent text-ink-soft hover:text-leaf-700'}`}>
                <Icon name={t.icon} className="h-[18px] w-[18px]" />
                {t.label}
                {Boolean(t.badge) && <Badge value={t.badge!} />}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main className={`mx-auto max-w-7xl px-4 pt-5 sm:px-6 md:pb-12 lg:px-8 ${manyTabs ? 'pb-12' : 'pb-28'}`}>
        {children}
      </main>

      {tabs.length > 1 && !manyTabs && !hideMobileNav && (
        <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
          <ul className="grid" style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}>
            {tabs.map((t) => (
              <li key={t.to}>
                <Link to={t.to} aria-current={isActive(t) ? 'page' : undefined}
                  className={`relative flex min-h-[60px] flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-semibold ${isActive(t) ? 'text-leaf-700' : 'text-gray-400'}`}>
                  <Icon name={t.icon} className="h-6 w-6" />
                  <span className="max-w-full truncate">{t.label}</span>
                  {Boolean(t.badge) && <span className="absolute right-[18%] top-1.5"><Badge value={t.badge!} /></span>}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  )
}

function Badge({ value }: { value: number }) {
  return <span className="min-w-[18px] rounded-full bg-mango-400 px-1 text-center text-[11px] font-bold leading-[18px] text-leaf-950">{value}</span>
}

/** Name + avatar opening a small menu (hover on desktop, tap on phones). */
function AccountMenu({ user, items }: { user: AuthUser; items: MenuItem[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  const choose = (item: MenuItem) => {
    setOpen(false)
    if (item.to) navigate(item.to)
    item.onClick?.()
  }
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')

  return (
    <div ref={ref} className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-xl py-1 pl-1.5 pr-1 hover:bg-gray-50">
        <span className="hidden text-right sm:block">
          <span className="block text-sm font-bold leading-tight text-leaf-900">{user.name}</span>
          <span className="block text-xs font-semibold text-ink-soft">{ROLE_LABELS[user.role]}</span>
        </span>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mango-300 text-sm font-extrabold text-leaf-900 sm:h-10 sm:w-10" aria-hidden="true">
          {initials}
        </span>
        <Icon name="chevronDown" className={`h-4 w-4 text-ink-soft transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-40 w-64 pt-1">
          <div className="rounded-xl border border-gray-200 bg-white p-1.5 shadow-lg">
            <p className="px-3 pb-1.5 pt-1 text-xs text-ink-soft sm:hidden">{user.name} · {ROLE_LABELS[user.role]}</p>
            {items.map((item) => (
              <button key={item.label} type="button" role="menuitem" onClick={() => choose(item)}
                className={`flex min-h-11 w-full items-center justify-between gap-3 rounded-lg px-3 text-left text-sm font-semibold hover:bg-gray-50 ${item.danger ? 'text-red-700' : 'text-ink'}`}>
                <span>{item.label}</span>
                {item.trailing}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
