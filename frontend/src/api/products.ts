import { apiRequest } from './client'

export interface Category {
  id: string
  name: string
}

export interface Scheme {
  id: string
  scheme_type: 'FREE_GOODS' | 'SLAB_DISCOUNT'
  description: string
  min_quantity: string
  free_quantity: string
  discount_percentage: string
}

/** Decimal values arrive as strings and are only displayed, never used to compute prices. */
export interface Product {
  id: string
  sku: string
  name: string
  brand: string
  category: Category
  pack_size: string
  units_per_case: string
  base_unit: string
  order_unit: string
  gst_rate: string
  image_url: string | null // large optimized image (Cloudinary), null: show placeholder
  thumbnail_url: string | null
  price: { dealer_price: string; price_basis: 'PIECE' | 'CASE'; tax_inclusive: boolean; case_price: string }
  stock_cases: string
  in_stock: boolean
  schemes: Scheme[]
}

export interface ProductPage {
  items: Product[]
  page: number
  limit: number
  total: number
}

export const fetchCategories = (token: string, signal?: AbortSignal) =>
  apiRequest<Category[]>('/products/categories', { token, signal })

export const fetchProducts = (
  token: string,
  params: { search?: string; category_id?: string; page?: number; limit?: number; retailer_id?: string; has_scheme?: boolean },
  signal?: AbortSignal,
) =>
  apiRequest<ProductPage>('/products', {
    token,
    params: { ...params, has_scheme: params.has_scheme ? 'true' : undefined },
    signal,
  })

export const fetchProduct = (token: string, id: string, signal?: AbortSignal) =>
  apiRequest<Product>(`/products/${id}`, { token, signal })
