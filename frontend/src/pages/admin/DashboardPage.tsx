import { admin } from '../../api/admin'
import { useLoad } from '../../auth/useApi'
import { Link } from '../../components/Link'
import { SourceBadge, StatusBadge } from '../../components/ui'
import { dateTime, qty, rupees } from '../../format'
import { AdminPage, Card, Loaded, Stat } from './adminUi'

/** Business overview for the Admin: counts, money, issues and recent activity. */
export function DashboardPage() {
  const data = useLoad((t, s) => admin.dashboard(t, s), 'admin-dashboard')
  return (
    <Loaded state={data.state} reload={data.reload} label="Loading dashboard…">
      {(d) => (
        <AdminPage title="Dashboard" subtitle={d.business_name}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat icon="store" label="Retailers" value={d.retailers_total} hint={`${d.retailers_active} active · ${d.retailers_total - d.retailers_active} inactive`} />
            <Stat icon="users" label="Salesmen" value={d.salesmen_total} hint={`${d.salesmen_active} active`} />
            <Stat icon="box" label="Products / SKUs" value={d.products_total} hint={`${d.products_active} active`} />
            <Stat icon="inbox" label="Orders today" value={d.orders_today} hint="All sources" />
            <Stat icon="clock" label="Pending review" value={d.pending} tone={d.pending ? 'warn' : 'plain'} hint="At the order desk" />
            <Stat icon="help" label="Needs clarification" value={d.clarification} tone={d.clarification ? 'warn' : 'plain'} />
            <Stat icon="checkCircle" label="Confirmed orders" value={d.confirmed} tone="good" hint={`${d.rejected} rejected`} />
            <Stat icon="rupee" label="Confirmed value" value={rupees(d.confirmed_value_30d)} hint={`Last 30 days · today ${rupees(d.confirmed_value_today)} · all time ${rupees(d.confirmed_value_total)}`} />
            <Stat icon="wallet" label="Outstanding credit" value={rupees(d.outstanding_total)} hint={`of ${rupees(d.credit_limit_total)} total limits`} />
            <Stat icon="alert" label="Low-stock products" value={d.low_stock_count} tone={d.low_stock_count ? 'bad' : 'plain'} hint={`${qty(d.low_stock_threshold)} cases or fewer`} />
            <Stat icon="history" label="Not ordered recently" value={d.inactive_count} tone={d.inactive_count ? 'warn' : 'plain'} hint={`No order in ${d.inactive_days} days`} />
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card title="Recent orders" actions={<Link to="/admin/orders" className="text-sm font-bold text-leaf-700">All orders →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.recent_orders.map((o) => (
                  <li key={o.id}>
                    <Link to={`/desk/orders/${o.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-gray-50">
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink">{o.retailer.shop_name}</span>
                        <span className="text-xs text-ink-soft">{o.order_number} · {dateTime(o.created_at)} · <SourceBadge source={o.source} /></span>
                      </span>
                      <span className="shrink-0 text-right"><span className="block font-bold">{rupees(o.grand_total)}</span><StatusBadge status={o.status} /></span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Recent salesman activity" actions={<Link to="/admin/salesmen" className="text-sm font-bold text-leaf-700">Salesmen →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.recent_visits.length === 0 && <li className="px-4 py-6 text-sm text-ink-soft">No visits yet.</li>}
                {d.recent_visits.map((v, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold text-ink">{v.salesman} visited {v.shop_name}</span>
                      <span className="text-xs text-ink-soft">{dateTime(v.started_at)}</span>
                    </span>
                    <span className="shrink-0 text-right text-xs">{v.order_number ? <><span className="block font-bold text-ink">{rupees(v.order_total ?? 0)}</span>{v.order_number}</> : <span className="text-ink-soft">{v.ended_at ? 'No order' : 'In progress'}</span>}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Low stock" actions={<Link to="/admin/stock?filter=low" className="text-sm font-bold text-leaf-700">Stock →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.low_stock.length === 0 && <li className="px-4 py-6 text-sm text-ink-soft">No product is low on stock.</li>}
                {d.low_stock.map(({ product, stock }) => (
                  <li key={product.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <Link to={`/admin/products/${product.id}`} className="min-w-0 truncate font-semibold text-ink hover:text-leaf-700">{product.name}<span className="ml-1 text-xs font-normal text-ink-soft">{product.sku}</span></Link>
                    <span className={`shrink-0 font-bold ${Number(stock) <= 0 ? 'text-red-700' : 'text-mango-600'}`}>{Number(stock) <= 0 ? 'Out of stock' : `${qty(stock)} cases`}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title={`No order in ${d.inactive_days} days`} actions={<Link to="/admin/reports?report=inactive-retailers" className="text-sm font-bold text-leaf-700">Report →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.inactive.length === 0 && <li className="px-4 py-6 text-sm text-ink-soft">Every active retailer ordered recently.</li>}
                {d.inactive.map(({ retailer, last_order_at }) => (
                  <li key={retailer.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <Link to={`/admin/retailers/${retailer.id}`} className="min-w-0 truncate font-semibold text-ink hover:text-leaf-700">{retailer.shop_name}</Link>
                    <span className="shrink-0 text-xs text-ink-soft">{last_order_at ? `Last order ${dateTime(last_order_at)}` : 'Never ordered'} · {retailer.salesman?.name ?? 'No salesman'}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Recently added retailers" actions={<Link to="/admin/retailers?sort=newest" className="text-sm font-bold text-leaf-700">Retailers →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.recent_retailers.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <Link to={`/admin/retailers/${r.id}`} className="min-w-0 truncate font-semibold text-ink hover:text-leaf-700">{r.shop_name}</Link>
                    <span className="shrink-0 text-xs text-ink-soft">{r.city} · {dateTime(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Recently added products" actions={<Link to="/admin/products" className="text-sm font-bold text-leaf-700">Products →</Link>} padded={false}>
              <ul className="divide-y divide-gray-100">
                {d.recent_products.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <Link to={`/admin/products/${p.id}`} className="min-w-0 truncate font-semibold text-ink hover:text-leaf-700">{p.name}</Link>
                    <span className="shrink-0 text-xs text-ink-soft">{p.brand} · {dateTime(p.created_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </AdminPage>
      )}
    </Loaded>
  )
}
