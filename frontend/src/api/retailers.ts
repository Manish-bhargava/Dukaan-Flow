import { apiRequest } from './client'

/** Money values arrive as decimal strings and are only displayed. */
export interface RetailerProfile {
  id: string
  shop_name: string
  owner_name: string
  phone: string
  address: string
  city: string
  gstin: string | null
  assigned_salesman: { name: string; phone: string } | null
  credit: { credit_limit: string; current_outstanding: string; reserved_for_review: string; available_credit: string } | null
  can_place_orders: boolean
  purchases: {
    total_orders: number
    confirmed_orders: number
    total_purchased: string
    under_review_orders: number
    under_review_amount: string
    rejected_orders: number
  }
}

export const fetchMyProfile = (token: string, signal?: AbortSignal) =>
  apiRequest<RetailerProfile>('/retailers/me', { token, signal })
