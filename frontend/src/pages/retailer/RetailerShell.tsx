import { t } from '../../i18n'
import { LanguageToggle } from '../../components/LanguageToggle'
import { useEffect, type ReactNode } from 'react'
import type { AuthUser } from '../../api/auth'
import { fetchMyProfile } from '../../api/retailers'
import { useAuth } from '../../auth/AuthContext'
import { useLoad } from '../../auth/useApi'
import { useCart } from '../../cart/CartContext'
import { AppShell, type NavTab } from '../../components/AppShell'
import { CREDIT_LEVEL_STYLES, creditLevel, rupees } from '../../format'
import { usePathname } from '../../router'

export function RetailerShell({ user, children }: { user: AuthUser; children: ReactNode }) {
  const { signOut } = useAuth()
  const { count } = useCart()
  const pathname = usePathname()
  // The retailer's own credit for the menu; refreshed on navigation and when the tab regains focus.
  const profile = useLoad((t, s) => fetchMyProfile(t, s), `header-credit-${pathname}`)
  const { reload } = profile
  useEffect(() => {
    window.addEventListener('focus', reload)
    return () => window.removeEventListener('focus', reload)
  }, [reload])
  const credit = profile.state.status === 'ready' ? profile.state.data.credit : null

  const tabs: NavTab[] = [
    { to: '/home', label: t('Catalogue'), icon: 'grid', match: (p) => p.startsWith('/products/') },
    { to: '/offers', label: t('Offers'), icon: 'tag' },
    { to: '/ai-order', label: t('AI Order'), icon: 'sparkles' },
    { to: '/orders', label: t('My orders'), icon: 'orders', match: (p) => p.startsWith('/orders/') },
    { to: '/cart', label: t('Cart'), icon: 'cart', badge: count },
  ]

  return (
    <AppShell
      user={user}
      tabs={tabs}
      status={<LanguageToggle />}
      menu={[
        {
          label: t('Credit details'),
          to: '/credit',
          trailing: credit && (
            <span className={`rounded-md px-2 py-0.5 text-xs font-extrabold ring-1 ${CREDIT_LEVEL_STYLES[creditLevel(credit.available_credit, credit.credit_limit)].pill}`}>
              {t('{amount} left', { amount: rupees(Math.max(0, Number(credit.available_credit))) })}
            </span>
          ),
        },
        { label: t('View profile'), to: '/profile' },
        { label: t('Log out'), onClick: () => signOut(), danger: true },
      ]}
    >
      {children}
    </AppShell>
  )
}
