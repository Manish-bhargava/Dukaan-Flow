import type { ReactNode } from 'react'
import type { Order, OrderItem } from '../api/orders'
import { gstLabel, plural, qty, rupees } from '../format'

/** An order's lines from their stored snapshots (price, scheme, GST as when ordered). */
export function OrderLines({ order, actions }: { order: Order; actions?: (item: OrderItem) => ReactNode }) {
  return (
    <ul className="divide-y divide-gray-200 border-y border-gray-200">
      {order.items.map((item) => (
        <li key={item.id} className="py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-bold text-ink">{item.product_name}</p>
              <p className="text-xs text-ink-soft">
                {item.sku} · {item.pack_size}
              </p>
            </div>
            <p className="shrink-0 text-lg font-extrabold text-ink">{rupees(item.line_total)}</p>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-5">
            <Cell label="Ordered">{plural(item.paid_quantity, item.order_unit)}</Cell>
            <Cell label="Free">{Number(item.free_quantity) > 0 ? plural(item.free_quantity, item.order_unit) : '—'}</Cell>
            <Cell label="Rate">
              {rupees(item.unit_price)} / {item.price_basis === 'PIECE' ? 'piece' : item.order_unit}
            </Cell>
            <Cell label="Discount">{Number(item.discount_amount) > 0 ? `${qty(item.discount_percentage)}% · −${rupees(item.discount_amount)}` : '—'}</Cell>
            <Cell label="GST">
              {gstLabel(item.gst_rate, item.tax_inclusive)} · {rupees(item.gst_amount)}
            </Cell>
          </dl>
          {item.scheme && <p className="mt-2 text-sm font-bold text-mango-600">Scheme: {item.scheme.description}</p>}
          {item.corrections.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-ink-soft">
              {item.corrections.map((c) => (
                <li key={c.created_at}>
                  Corrected by order desk: {qty(c.old_quantity)} → {qty(c.new_quantity)}
                  {c.old_product_id && c.old_product_id !== c.new_product_id ? ' (product changed)' : ''}
                  {c.reason ? ` · ${c.reason}` : ''}
                </li>
              ))}
            </ul>
          )}
          {actions?.(item)}
        </li>
      ))}
    </ul>
  )
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="font-semibold text-ink">{children}</dd>
    </div>
  )
}
