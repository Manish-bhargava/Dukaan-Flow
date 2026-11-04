import type { ReactNode } from 'react'
import { ROLE_LABELS, type AuthUser } from '../api/auth'
import { useAuth } from '../auth/AuthContext'
import { Logo } from './Logo'

export function AppHeader({ user, nav }: { user: AuthUser; nav?: ReactNode }) {
  const { signOut } = useAuth()
  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-8">
        <Logo to="/home" />
        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-sm font-bold leading-tight text-leaf-900">{user.name}</p>
            <p className="text-xs font-semibold text-ink-soft">{ROLE_LABELS[user.role]}</p>
          </div>
          <button
            type="button"
            onClick={() => signOut()}
            className="min-h-10 rounded-lg px-3 text-sm font-bold text-leaf-700 ring-1 ring-gray-300 hover:bg-gray-50"
          >
            Log out
          </button>
        </div>
      </div>
      {nav}
    </header>
  )
}
