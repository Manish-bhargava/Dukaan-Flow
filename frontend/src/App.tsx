import type { AuthUser } from './api/auth'
import { useAuth } from './auth/AuthContext'
import { CartProvider } from './cart/CartContext'
import { AppHeader } from './components/AppHeader'
import { Redirect } from './components/Link'
import { FullPageLoader } from './components/Spinner'
import { DeskDashboard } from './pages/desk/DeskDashboard'
import { DeskOrderPage } from './pages/desk/DeskOrderPage'
import { StaffHomePage } from './pages/HomePage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { AiOrderPage } from './pages/retailer/AiOrderPage'
import { CartPage } from './pages/retailer/CartPage'
import { CataloguePage } from './pages/retailer/CataloguePage'
import { OffersPage } from './pages/retailer/OffersPage'
import { ProductDetailPage } from './pages/retailer/ProductDetailPage'
import { OrderDetailPage } from './pages/retailer/OrderDetailPage'
import { OrdersPage } from './pages/retailer/OrdersPage'
import { RetailerShell } from './pages/retailer/RetailerShell'
import { usePathname } from './router'

/**
 * Routes (the backend enforces the same role rules on every API call):
 *   /, /login                public; signed-in users go to /home
 *   RETAILER                 /home (catalogue), /products/:id, /offers, /cart, /ai-order, /orders, /orders/:id
 *   ORDER_DESK, ADMIN        /home (order desk), /desk/orders/:id
 *   SALESMAN                 /home
 */
function App() {
  const { state } = useAuth()
  const pathname = usePathname()

  if (state.status === 'loading') return <FullPageLoader label="Checking your session…" />
  const signedIn = state.status === 'authenticated'

  if (pathname === '/') return signedIn ? <Redirect to="/home" /> : <LandingPage />
  if (pathname === '/login') return signedIn ? <Redirect to="/home" /> : <LoginPage />
  if (!signedIn) return <Redirect to="/login" />
  return <SignedIn user={state.user} pathname={pathname} />
}

const idFrom = (pathname: string, prefix: string) => {
  const match = new RegExp(`^${prefix}/([0-9a-f-]{36})$`).exec(pathname)
  return match?.[1]
}

function SignedIn({ user, pathname }: { user: AuthUser; pathname: string }) {
  if (user.role === 'RETAILER') {
    const orderId = idFrom(pathname, '/orders')
    const productId = idFrom(pathname, '/products')
    const page =
      pathname === '/home' ? <CataloguePage />
      : pathname === '/offers' ? <OffersPage />
      : pathname === '/cart' ? <CartPage />
      : pathname === '/ai-order' ? <AiOrderPage />
      : pathname === '/orders' ? <OrdersPage />
      : orderId ? <OrderDetailPage key={orderId} orderId={orderId} />
      : productId ? <ProductDetailPage key={productId} productId={productId} />
      : null
    if (!page) return <Redirect to="/home" />
    return (
      <CartProvider userId={user.id}>
        <RetailerShell user={user}>{page}</RetailerShell>
      </CartProvider>
    )
  }

  if (user.role === 'ORDER_DESK' || user.role === 'ADMIN') {
    const orderId = idFrom(pathname, '/desk/orders')
    const page = pathname === '/home' ? <DeskDashboard /> : orderId ? <DeskOrderPage key={orderId} orderId={orderId} /> : null
    if (!page) return <Redirect to="/home" />
    return (
      <div className="min-h-screen bg-white">
        <AppHeader user={user} />
        <main className="mx-auto max-w-7xl px-4 pb-16 pt-5 sm:px-8">{page}</main>
      </div>
    )
  }

  return pathname === '/home' ? <StaffHomePage user={user} /> : <Redirect to="/home" />
}

export default App
