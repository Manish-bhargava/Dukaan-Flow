import { lazy, Suspense } from 'react'
import type { Section } from './pages/desk/DeskOrdersPage'
import type { AuthUser } from './api/auth'
import { useAuth } from './auth/AuthContext'
import { CartProvider } from './cart/CartContext'
import { AppShell } from './components/AppShell'
import { Redirect } from './components/Link'
import { FullPageLoader } from './components/Spinner'
import { Loading } from './components/ui'
import type { NavGroup, NavTab } from './components/AppShell'
import { LoginPage } from './pages/LoginPage'
import { CataloguePage } from './pages/retailer/CataloguePage'
import { RetailerShell } from './pages/retailer/RetailerShell'
import { usePathname } from './router'

// Staff screens (admin, order desk) load on demand, so retailers and salesmen on slow
// phones download only their own screens. Salesman screens stay in the main bundle (offline use).
const AiOrdersPage = lazy(() => import('./pages/admin/MonitoringPages').then((m) => ({ default: m.AiOrdersPage })))
const OrderDeskOversightPage = lazy(() => import('./pages/admin/MonitoringPages').then((m) => ({ default: m.OrderDeskOversightPage })))
const SyncMonitorPage = lazy(() => import('./pages/admin/MonitoringPages').then((m) => ({ default: m.SyncMonitorPage })))
const AuditPage = lazy(() => import('./pages/admin/AuditPage').then((m) => ({ default: m.AuditPage })))
const CatalogSetupPage = lazy(() => import('./pages/admin/CatalogSetupPage').then((m) => ({ default: m.CatalogSetupPage })))
const DashboardPage = lazy(() => import('./pages/admin/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const PricingPage = lazy(() => import('./pages/admin/PricingPage').then((m) => ({ default: m.PricingPage })))
const ReportsPage = lazy(() => import('./pages/admin/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const SchemesPage = lazy(() => import('./pages/admin/SchemesPage').then((m) => ({ default: m.SchemesPage })))
const SettingsPage = lazy(() => import('./pages/admin/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const StockPage = lazy(() => import('./pages/admin/StockPage').then((m) => ({ default: m.StockPage })))
const UsersPage = lazy(() => import('./pages/admin/UsersPage').then((m) => ({ default: m.UsersPage })))
const DeskOrderPage = lazy(() => import('./pages/desk/DeskOrderPage').then((m) => ({ default: m.DeskOrderPage })))
const DeskOverview = lazy(() => import('./pages/desk/DeskOverview').then((m) => ({ default: m.DeskOverview })))
const DispatchPage = lazy(() => import('./pages/desk/DispatchPage').then((m) => ({ default: m.DispatchPage })))
const AdminCreditPage = lazy(() => import('./pages/admin/CreditPage').then((m) => ({ default: m.CreditPage })))
const AdminProductPage = lazy(() => import('./pages/admin/ProductPages').then((m) => ({ default: m.ProductDetailPage })))
const ProductsPage = lazy(() => import('./pages/admin/ProductPages').then((m) => ({ default: m.ProductsPage })))
const AdminRetailerPage = lazy(() => import('./pages/admin/RetailerPages').then((m) => ({ default: m.RetailerDetailPage })))
const RetailersPage = lazy(() => import('./pages/admin/RetailerPages').then((m) => ({ default: m.RetailersPage })))
const AssignmentsPage = lazy(() => import('./pages/admin/SalesmanPages').then((m) => ({ default: m.AssignmentsPage })))
const SalesmanDetailPage = lazy(() => import('./pages/admin/SalesmanPages').then((m) => ({ default: m.SalesmanDetailPage })))
const SalesmenPage = lazy(() => import('./pages/admin/SalesmanPages').then((m) => ({ default: m.SalesmenPage })))
const LandingPage = lazy(() => import('./pages/LandingPage').then((m) => ({ default: m.LandingPage })))
const AiOrderPage = lazy(() => import('./pages/retailer/AiOrderPage').then((m) => ({ default: m.AiOrderPage })))
const CartPage = lazy(() => import('./pages/retailer/CartPage').then((m) => ({ default: m.CartPage })))
const OffersPage = lazy(() => import('./pages/retailer/OffersPage').then((m) => ({ default: m.OffersPage })))
const ProductDetailPage = lazy(() => import('./pages/retailer/ProductDetailPage').then((m) => ({ default: m.ProductDetailPage })))
const CreditPage = lazy(() => import('./pages/retailer/ProfilePage').then((m) => ({ default: m.CreditPage })))
const ProfilePage = lazy(() => import('./pages/retailer/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const OrderDetailPage = lazy(() => import('./pages/retailer/OrderDetailPage').then((m) => ({ default: m.OrderDetailPage })))
const OrdersPage = lazy(() => import('./pages/retailer/OrdersPage').then((m) => ({ default: m.OrdersPage })))
const SalesmanApp = lazy(() => import('./pages/salesman/SalesmanApp').then((m) => ({ default: m.SalesmanApp })))
const DeskOrdersPage = lazy(() => import('./pages/desk/DeskOrdersPage').then((m) => ({ default: m.DeskOrdersPage })))


/**
 * Routes (the backend enforces the same role rules on every API call):
 *   /, /login                public; signed-in users go to /home
 *   RETAILER                 /home (catalogue), /products/:id, /offers, /profile, /credit, /cart, /ai-order, /orders, /orders/:id
 *   ADMIN                    /home (dashboard), /admin/* (sidebar), plus the order desk pages /desk/* for oversight
 *   ORDER_DESK               /home (overview), /desk/incoming, /desk/confirmed, /desk/rejected,
 *                            /desk/clarification, /desk/dispatch, /desk/history, /desk/orders/:id
 *   SALESMAN                 /home, /salesman/retailers, /salesman/retailers/:id, /salesman/visit/:retailerId(/review),
 *                            /salesman/orders, /salesman/orders/:id, /salesman/orders/local/:clientId,
 *                            /salesman/sync, /salesman/profile
 */
function App() {
  const { state } = useAuth()
  const pathname = usePathname()

  if (state.status === 'loading') return <FullPageLoader label="Checking your session…" />
  const signedIn = state.status === 'authenticated'

  if (pathname === '/') return signedIn ? <Redirect to="/home" /> : <Suspense fallback={<FullPageLoader label="Loading…" />}><LandingPage /></Suspense>
  if (pathname === '/login') return signedIn ? <Redirect to="/home" /> : <LoginPage />
  if (!signedIn) return <Redirect to="/login" />
  return <SignedIn user={state.user} pathname={pathname} />
}

const idFrom = (pathname: string, prefix: string) => {
  const match = new RegExp(`^${prefix}/([0-9a-f-]{36})$`).exec(pathname)
  return match?.[1]
}

function SignedIn({ user, pathname }: { user: AuthUser; pathname: string }) {
  const { signOut } = useAuth()
  if (user.role === 'RETAILER') {
    const orderId = idFrom(pathname, '/orders')
    const productId = idFrom(pathname, '/products')
    const page =
      pathname === '/home' ? <CataloguePage />
      : pathname === '/offers' ? <OffersPage />
      : pathname === '/profile' ? <ProfilePage />
      : pathname === '/credit' ? <CreditPage />
      : pathname === '/cart' ? <CartPage />
      : pathname === '/ai-order' ? <AiOrderPage />
      : pathname === '/orders' ? <OrdersPage />
      : orderId ? <OrderDetailPage key={orderId} orderId={orderId} />
      : productId ? <ProductDetailPage key={productId} productId={productId} />
      : null
    if (!page) return <Redirect to="/home" />
    return (
      <CartProvider userId={user.id}>
        <RetailerShell user={user}><Suspense fallback={<Loading />}>{page}</Suspense></RetailerShell>
      </CartProvider>
    )
  }

  if (user.role === 'ADMIN') {
    const id = (prefix: string) => idFrom(pathname, prefix)
    const section = /^\/desk\/(incoming|confirmed|rejected|clarification|history)$/.exec(pathname)?.[1] as Section | undefined
    const page =
      pathname === '/home' ? <DashboardPage />
      : pathname === '/admin/orders' ? <DeskOrdersPage key="admin-orders" section="history" />
      : pathname === '/admin/order-desk' ? <OrderDeskOversightPage />
      : pathname === '/admin/ai-orders' ? <AiOrdersPage />
      : pathname === '/admin/sync' ? <SyncMonitorPage />
      : pathname === '/admin/retailers' ? <RetailersPage />
      : id('/admin/retailers') ? <AdminRetailerPage key={id('/admin/retailers')} retailerId={id('/admin/retailers')!} />
      : pathname === '/admin/salesmen' ? <SalesmenPage />
      : id('/admin/salesmen') ? <SalesmanDetailPage key={id('/admin/salesmen')} salesmanId={id('/admin/salesmen')!} />
      : pathname === '/admin/assignments' ? <AssignmentsPage />
      : pathname === '/admin/credit' ? <AdminCreditPage />
      : pathname === '/admin/users' ? <UsersPage />
      : pathname === '/admin/products' ? <ProductsPage />
      : id('/admin/products') ? <AdminProductPage key={id('/admin/products')} productId={id('/admin/products')!} />
      : pathname === '/admin/catalogue' ? <CatalogSetupPage />
      : pathname === '/admin/pricing' ? <PricingPage />
      : pathname === '/admin/schemes' ? <SchemesPage />
      : pathname === '/admin/stock' ? <StockPage />
      : pathname === '/admin/reports' ? <ReportsPage />
      : pathname === '/admin/audit' ? <AuditPage />
      : pathname === '/admin/settings' ? <SettingsPage />
      : section ? <DeskOrdersPage key={section} section={section} />
      : pathname === '/desk/dispatch' ? <DispatchPage />
      : id('/desk/orders') ? <DeskOrderPage key={id('/desk/orders')} orderId={id('/desk/orders')!} />
      : null
    if (!page) return <Redirect to="/home" />
    return (
      <AppShell user={user} tabs={[]} sidebar={ADMIN_NAV} menu={[{ label: 'Log out', onClick: () => signOut(), danger: true }]}>
        <Suspense fallback={<Loading />}>{page}</Suspense>
      </AppShell>
    )
  }

  if (user.role === 'ORDER_DESK') {
    const orderId = idFrom(pathname, '/desk/orders')
    const section = /^\/desk\/(incoming|confirmed|rejected|clarification|history)$/.exec(pathname)?.[1] as Section | undefined
    const page =
      pathname === '/home' ? <DeskOverview />
      : section ? <DeskOrdersPage key={section} section={section} />
      : pathname === '/desk/dispatch' ? <DispatchPage />
      : orderId ? <DeskOrderPage key={orderId} orderId={orderId} />
      : null
    if (!page) return <Redirect to="/home" />
    return (
      <AppShell user={user} tabs={DESK_TABS}
        menu={[{ label: 'Log out', onClick: () => signOut(), danger: true }]}>
        <Suspense fallback={<Loading />}>{page}</Suspense>
      </AppShell>
    )
  }

  // SALESMAN (works offline from the phone's saved data). Loaded only for salesmen, as soon
  // as they sign in (online); the service worker then keeps it for use without signal.
  return <Suspense fallback={<FullPageLoader label="Opening…" />}><SalesmanApp user={user} pathname={pathname} /></Suspense>
}

const DESK_TABS: NavTab[] = [
  { to: '/home', label: 'Overview', icon: 'grid' },
  { to: '/desk/incoming', label: 'Incoming', icon: 'inbox' },
  { to: '/desk/confirmed', label: 'Confirmed', icon: 'checkCircle' },
  { to: '/desk/rejected', label: 'Rejected', icon: 'xCircle' },
  { to: '/desk/clarification', label: 'Clarification', icon: 'help' },
  { to: '/desk/dispatch', label: 'Dispatch', icon: 'truck' },
  { to: '/desk/history', label: 'History', icon: 'history' },
]

const ADMIN_NAV: NavGroup[] = [
  { title: 'Overview', tabs: [{ to: '/home', label: 'Dashboard', icon: 'grid' }] },
  { title: 'Orders', tabs: [
    { to: '/admin/orders', label: 'All orders', icon: 'orders', match: (p) => p.startsWith('/desk/orders/') },
    { to: '/admin/order-desk', label: 'Order desk', icon: 'inbox', match: (p) => p.startsWith('/desk/') && !p.startsWith('/desk/orders/') },
    { to: '/admin/ai-orders', label: 'AI orders', icon: 'sparkles' },
    { to: '/admin/sync', label: 'Offline sync', icon: 'sync' },
  ] },
  { title: 'People', tabs: [
    { to: '/admin/retailers', label: 'Retailers', icon: 'store', match: (p) => p.startsWith('/admin/retailers/') },
    { to: '/admin/salesmen', label: 'Salesmen', icon: 'users', match: (p) => p.startsWith('/admin/salesmen/') },
    { to: '/admin/assignments', label: 'Assignments', icon: 'link' },
    { to: '/admin/credit', label: 'Credit', icon: 'wallet' },
    { to: '/admin/users', label: 'Users & roles', icon: 'shield' },
  ] },
  { title: 'Catalogue', tabs: [
    { to: '/admin/products', label: 'Products', icon: 'box', match: (p) => p.startsWith('/admin/products/') },
    { to: '/admin/catalogue', label: 'Categories & brands', icon: 'layers' },
    { to: '/admin/pricing', label: 'Pricing', icon: 'rupee' },
    { to: '/admin/schemes', label: 'Schemes', icon: 'percent' },
    { to: '/admin/stock', label: 'Stock', icon: 'truck' },
  ] },
  { title: 'Insights', tabs: [
    { to: '/admin/reports', label: 'Reports', icon: 'chart' },
    { to: '/admin/audit', label: 'Audit log', icon: 'history' },
  ] },
  { title: 'System', tabs: [{ to: '/admin/settings', label: 'Settings', icon: 'settings' }] },
]

export default App
