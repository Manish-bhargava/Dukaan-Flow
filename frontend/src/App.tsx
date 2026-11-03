import { useAuth } from './auth/AuthContext'
import { FullPageLoader } from './components/Spinner'
import { HomePage } from './pages/HomePage'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { Redirect } from './components/Link'
import { usePathname } from './router'

/**
 * Routes:
 *   /       public landing page  (signed in → /home)
 *   /login  OTP / password login (signed in → /home)
 *   /home   role-based home      (signed out → /login)
 */
function App() {
  const { state } = useAuth()
  const pathname = usePathname()

  if (state.status === 'loading') return <FullPageLoader label="Checking your session…" />
  const signedIn = state.status === 'authenticated'

  switch (pathname) {
    case '/':
      return signedIn ? <Redirect to="/home" /> : <LandingPage />
    case '/login':
      return signedIn ? <Redirect to="/home" /> : <LoginPage />
    case '/home':
      return signedIn ? <HomePage user={state.user} token={state.session.token} /> : <Redirect to="/login" />
    default:
      return <Redirect to={signedIn ? '/home' : '/'} />
  }
}

export default App
