import { Link } from './Link'

export function LogoMark({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <rect width="48" height="48" rx="12" fill="#176036" />
      <path d="M9 17h30l-2.5-6.5h-25z" fill="#fbc124" />
      <path
        d="M9 17c0 2.5 2 4 4.3 4s4.2-1.5 4.2-4c0 2.5 2.1 4 4.3 4s4.2-1.5 4.2-4c0 2.5 2 4 4.3 4s4.2-1.5 4.2-4c0 2.5 2 4 4.3 4"
        fill="none" stroke="#fffdf7" strokeWidth="2.4" strokeLinecap="round"
      />
      <path d="M13 24v13h22V24" fill="none" stroke="#fffdf7" strokeWidth="2.6" strokeLinejoin="round" />
      <path d="M18 32.5c2.7-3 7.3-3 12 0" fill="none" stroke="#fbc124" strokeWidth="2.6" strokeLinecap="round" />
      <path d="m27.5 29.6 2.8 2.9-3.6 1.5" fill="none" stroke="#fbc124" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Logo({ to = '/', light = false }: { to?: string; light?: boolean }) {
  return (
    <Link to={to} className="flex items-center gap-2.5" aria-label="DukaanFlow home">
      <LogoMark />
      <span className={`text-xl font-extrabold tracking-tight ${light ? 'text-cream-50' : 'text-leaf-800'}`}>
        Dukaan<span className={light ? 'text-mango-300' : 'text-mango-500'}>Flow</span>
      </span>
    </Link>
  )
}
