import { ROLE_LABELS, type AuthUser } from '../api/auth'
import { AppHeader } from '../components/AppHeader'
import { RetailerHome } from './RetailerHome'

/** Post-login home, chosen by the authenticated user's role. */
export function HomePage({ user, token }: { user: AuthUser; token: string }) {
  return (
    <div className="min-h-screen bg-cream-50">
      <AppHeader user={user} />
      {user.role === 'RETAILER' ? <RetailerHome user={user} token={token} /> : <StaffHome user={user} />}
    </div>
  )
}

const STAFF_WORK: Record<Exclude<AuthUser['role'], 'RETAILER'>, { title: string; items: string[] }> = {
  SALESMAN: {
    title: 'Your route',
    items: ['Book orders for your assigned shops', 'See each shop’s prices and credit', 'Follow up on orders on hold'],
  },
  ORDER_DESK: {
    title: 'Order desk',
    items: ['Review the incoming order queue', 'Correct items and quantities', 'Approve or reject orders, with credit checks'],
  },
  ADMIN: {
    title: 'Distributor admin',
    items: ['Business dashboard and inactive retailers', 'Manage retailers, prices and schemes', 'Export approved orders to Tally'],
  },
}

function StaffHome({ user }: { user: AuthUser }) {
  const work = STAFF_WORK[user.role as keyof typeof STAFF_WORK]
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8 sm:py-12">
      <section className="animate-fade-up overflow-hidden rounded-[2rem] bg-leaf-800 p-7 text-cream-50 sm:p-10">
        <span className="rounded-full bg-mango-300 px-3 py-1 text-xs font-bold uppercase tracking-wider text-leaf-950">
          {ROLE_LABELS[user.role]}
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Namaste, {user.name.split(' ')[0]}</h1>
        <p className="mt-2 max-w-xl text-leaf-100">You are signed in to DukaanFlow. Your workspace tools are listed below.</p>
      </section>

      <div className="mt-6 grid gap-5 md:grid-cols-[2fr_1fr]">
        <section className="rounded-3xl bg-white p-6 ring-1 ring-cream-200 sm:p-8">
          <h2 className="text-xl font-bold text-leaf-900">{work.title}</h2>
          <ul className="mt-5 space-y-3">
            {work.items.map((item) => (
              <li key={item} className="flex items-center justify-between gap-3 rounded-2xl bg-cream-50 px-4 py-3.5 ring-1 ring-cream-200">
                <span className="font-semibold text-ink">{item}</span>
                <span className="shrink-0 rounded-full bg-mango-100 px-2.5 py-1 text-xs font-bold text-mango-600">Coming soon</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="rounded-3xl bg-white p-6 ring-1 ring-cream-200 sm:p-8">
          <h2 className="text-xl font-bold text-leaf-900">Your account</h2>
          <dl className="mt-5 space-y-4 text-sm">
            <Row label="Name" value={user.name} />
            <Row label="Mobile" value={`+91 ${user.phone}`} />
            <Row label="Email" value={user.email ?? 'Not set'} />
            <Row label="Role" value={ROLE_LABELS[user.role]} />
          </dl>
        </section>
      </div>
    </main>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-semibold text-ink-soft">{label}</dt>
      <dd className="mt-0.5 break-all font-bold text-leaf-900">{value}</dd>
    </div>
  )
}
