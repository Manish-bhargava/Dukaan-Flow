import type { Product } from '../api/products'
import type { CartLine } from './CartContext'

export function cartLineFor(p: Product): Omit<CartLine, 'quantity'> {
  return { product_id: p.id, sku: p.sku, name: p.name, pack_size: p.pack_size, order_unit: p.order_unit, category: p.category.name }
}
