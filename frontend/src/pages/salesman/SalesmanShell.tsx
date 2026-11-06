import type { ReactNode } from 'react'
import type { AuthUser } from '../../api/auth'
import { useAuth } from '../../auth/AuthContext'
import { AppShell, type NavTab } from '../../components/AppShell'
import { Link } from '../../components/Link'
import { ago } from '../../format'
import { usePathname } from '../../router'
import { useSalesman } from '../../salesman/SalesmanContext'

/** Connection state shown in the header on every salesman screen. */
export function ConnectionPill() {
  const { online, syncing, pendingCount, lastSyncAt } = useSalesman()
  const s = !online
    ? { label: 'Offline', dot: 'bg-gray-400', style: 'bg-gray-800 text-white' }
    : syncing
      ? { label: 'Syncing…', dot: 'bg-sky-500 animate-pulse', style: 'bg-sky-50 text-sky-800' }
      : pendingCount > 0
        ? { label: `${pendingCount} to sync`, dot: 'bg-orange-500', style: 'bg-orange-50 text-orange-800' }
        : { label: 'Online', dot: 'bg-leaf-500', style: 'bg-leaf-50 text-leaf-800' }
  return (
    <Link to="/salesman/sync" role="status" title={lastSyncAt ? `Last synced ${ago(lastSyncAt)}` : 'Not synced yet'}
      className="inline-flex items-center gap-2">
      <span className={`inline-flex min-h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-[13px] font-semibold ${s.style}`}>
        <span className={`h-2 w-2 rounded-full ${s.dot}`} /> {s.label}
      </span>
      <span className="hidden whitespace-nowrap text-xs text-ink-soft lg:inline">
        {lastSyncAt ? `Synced ${ago(lastSyncAt)}` : 'Not synced yet'}
      </span>
    </Link>
  )
}

export function SalesmanShell({ user, children }: { user: AuthUser; children: ReactNode }) {
  const pathname = usePathname()
  const { signOut } = useAuth()
  const { needsLogin, online, pendingCount } = useSalesman()

  const tabs: NavTab[] = [
    { to: '/home', label: 'Home', icon: 'home' },
    { to: '/salesman/retailers', label: 'Retailers', icon: 'store', match: (p) => p.startsWith('/salesman/retailers/') || p.startsWith('/salesman/visit/') },
    { to: '/salesman/orders', label: 'Orders', icon: 'orders', match: (p) => p.startsWith('/salesman/orders/') },
    { to: '/salesman/sync', label: 'Sync', icon: 'sync', badge: pendingCount },
    { to: '/salesman/profile', label: 'Profile', icon: 'user' },
  ]
  const logOut = () => {
    if (pendingCount === 0 || window.confirm('Some orders are not synced yet. They stay saved on this phone and sync after you log in again. Log out?')) signOut()
  }

  return (
    <AppShell
      user={user}
      tabs={tabs}
      status={<ConnectionPill />}
      hideMobileNav={pathname.startsWith('/salesman/visit/')}
      banner={needsLogin && online ? (
        <div className="border-t border-orange-200 bg-orange-50 px-4 py-2 text-center text-[13px] text-orange-900">
          Login expired. Your saved orders are safe on this phone.{' '}
          <button type="button" className="font-semibold underline" onClick={() => signOut('Log in again to sync your saved orders.')}>Log in to sync</button>
        </div>
      ) : undefined}
      menu={[
        { label: 'My profile', to: '/salesman/profile' },
        { label: 'Offline sync', to: '/salesman/sync', trailing: pendingCount ? <span className="text-xs font-bold text-orange-700">{pendingCount} waiting</span> : undefined },
        { label: 'Log out', onClick: logOut, danger: true },
      ]}
    >
      {children}
    </AppShell>
  )
}
