import type { AuthUser } from '../../api/auth'
import { Redirect } from '../../components/Link'
import { SalesmanProvider } from '../../salesman/SalesmanContext'
import { RetailerDetailPage } from './RetailerDetailPage'
import { RetailerListPage } from './RetailerListPage'
import { SalesmanHome } from './SalesmanHome'
import { SalesmanLocalOrder, SalesmanServerOrder } from './SalesmanOrderDetail'
import { SalesmanOrdersPage } from './SalesmanOrdersPage'
import { SalesmanProfilePage } from './SalesmanProfilePage'
import { SalesmanShell } from './SalesmanShell'
import { SyncPage } from './SyncPage'
import { VisitPage } from './VisitPage'
import { VisitReviewPage } from './VisitReviewPage'

const idFrom = (pathname: string, prefix: string) => new RegExp(`^${prefix}/([0-9a-f-]{36})$`).exec(pathname)?.[1]

/** The salesman app (routes, offline data provider, shell): one chunk, loaded for salesmen only. */
export function SalesmanApp({ user, pathname }: { user: AuthUser; pathname: string }) {
  const retailerId = idFrom(pathname, '/salesman/retailers')
  const visitId = idFrom(pathname, '/salesman/visit')
  const reviewId = /^\/salesman\/visit\/([0-9a-f-]{36})\/review$/.exec(pathname)?.[1]
  const orderId = idFrom(pathname, '/salesman/orders')
  const localOrder = /^\/salesman\/orders\/local\/([0-9a-f]{32})$/.exec(pathname)?.[1]
  const page =
    pathname === '/home' ? <SalesmanHome name={user.name} />
    : pathname === '/salesman/retailers' ? <RetailerListPage />
    : retailerId ? <RetailerDetailPage key={retailerId} retailerId={retailerId} />
    : visitId ? <VisitPage key={visitId} retailerId={visitId} />
    : reviewId ? <VisitReviewPage key={reviewId} retailerId={reviewId} />
    : pathname === '/salesman/sync' ? <SyncPage />
    : pathname === '/salesman/profile' ? <SalesmanProfilePage user={user} />
    : pathname === '/salesman/orders' ? <SalesmanOrdersPage userId={user.id} />
    : localOrder ? <SalesmanLocalOrder clientOrderId={localOrder} />
    : orderId ? <SalesmanServerOrder key={orderId} orderId={orderId} />
    : null
  if (!page) return <Redirect to="/home" />
  return (
    <SalesmanProvider user={user}>
      <SalesmanShell user={user}>{page}</SalesmanShell>
    </SalesmanProvider>
  )
}
