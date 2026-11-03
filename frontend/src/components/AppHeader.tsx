import { ROLE_LABELS, type AuthUser } from '../api/auth'
import { useAuth } from '../auth/AuthContext'
import { Logo } from './Logo'

export function AppHeader({ user }: { user: AuthUser }) {
  const { signOut } = useAuth()
  return (
    <header className="sticky top-0 z-30 border-b border-cream-200 bg-cream-50/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-8">
        <Logo to="/home" />
        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-sm font-bold leading-tight text-leaf-900">{user.name}</p>
            <p className="text-xs font-semibold text-ink-soft">{ROLE_LABELS[user.role]}</p>
          </div>
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-mango-300 font-extrabold text-leaf-900" aria-hidden="true">
            {user.name.trim().charAt(0).toUpperCase()}
          </span>
          <button
            type="button"
            onClick={() => signOut()}
            className="rounded-full px-4 py-2 text-sm font-bold text-leaf-700 ring-1 ring-leaf-200 transition hover:bg-leaf-50"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  )
}
