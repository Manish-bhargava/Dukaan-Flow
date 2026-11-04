import type { ReactNode } from 'react'
import type { AuthUser } from '../../api/auth'
import { useCart } from '../../cart/CartContext'
import { AppHeader } from '../../components/AppHeader'
import { Link } from '../../components/Link'
import { usePathname } from '../../router'

const TABS = [
  { to: '/home', label: 'Catalogue' },
  { to: '/offers', label: 'Offers & Schemes' },
  { to: '/ai-order', label: 'Order by message' },
  { to: '/orders', label: 'My orders' },
]

export function RetailerShell({ user, children }: { user: AuthUser; children: ReactNode }) {
  const pathname = usePathname()
  const { count } = useCart()
  const active = (to: string) =>
    pathname === to || (to === '/orders' && pathname.startsWith('/orders/')) || (to === '/home' && pathname.startsWith('/products/'))
  const tab = (to: string, label: ReactNode) => (
    <Link
      key={to}
      to={to}
      aria-current={active(to) ? 'page' : undefined}
      className={`flex min-h-12 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-bold ${
        active(to) ? 'border-leaf-700 text-leaf-800' : 'border-transparent text-ink-soft hover:text-leaf-700'
      }`}
    >
      {label}
    </Link>
  )
  return (
    <div className="min-h-screen bg-white">
      <AppHeader
        user={user}
        nav={
          <nav className="mx-auto flex max-w-7xl overflow-x-auto px-2 sm:px-6" aria-label="Retailer">
            {TABS.map((t) => tab(t.to, t.label))}
            <span className="flex-1" />
            {tab(
              '/cart',
              <>
                Cart
                <span className={`min-w-6 rounded-full px-1.5 py-0.5 text-center text-xs ${count ? 'bg-mango-400 text-leaf-950' : 'bg-gray-100 text-ink-soft'}`}>
                  {count}
                </span>
              </>,
            )}
          </nav>
        }
      />
      <main className="mx-auto max-w-7xl px-4 pb-28 pt-5 sm:px-8">{children}</main>
    </div>
  )
}
