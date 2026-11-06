import type { Order } from '../api/orders'
import type { Product } from '../api/products'
import type { CartLine } from './CartContext'

export function cartLineFor(p: Product): Omit<CartLine, 'quantity'> {
  return { product_id: p.id, sku: p.sku, name: p.name, pack_size: p.pack_size, order_unit: p.order_unit, category: p.category.name }
}

/** An earlier order's products and paid quantities, to put in the cart again. Prices,
 *  schemes and stock are worked out afresh by the backend when the cart is priced. */
export function orderCartLines(order: Order): CartLine[] {
  return order.items.map((i) => ({
    product_id: i.product_id, sku: i.sku, name: i.product_name, pack_size: i.pack_size,
    order_unit: i.order_unit, category: '', quantity: Number(i.paid_quantity),
  }))
}
