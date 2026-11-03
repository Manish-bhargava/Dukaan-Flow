import { apiRequest } from './client'

export type UserRole = 'RETAILER' | 'SALESMAN' | 'ORDER_DESK' | 'ADMIN'

export const ROLE_LABELS: Record<UserRole, string> = {
  RETAILER: 'Retailer',
  SALESMAN: 'Salesman',
  ORDER_DESK: 'Order Desk',
  ADMIN: 'Admin',
}

export interface AuthUser {
  id: string
  name: string
  phone: string
  email: string | null
  role: UserRole
  retailer_id: string | null
  is_active: boolean
}

export interface TokenData {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface OtpRequestData {
  phone: string
  channel: 'email'
  expires_in: number
  resend_after: number
}

export const sendOtp = (phone: string) =>
  apiRequest<OtpRequestData>('/auth/send-otp', { method: 'POST', body: { phone } })

export const verifyOtp = (phone: string, otp: string) =>
  apiRequest<TokenData>('/auth/verify-otp', { method: 'POST', body: { phone, otp } })

export const loginWithPassword = (phone: string, password: string) =>
  apiRequest<TokenData>('/auth/login', { method: 'POST', body: { phone, password } })

export const fetchMe = (token: string, signal?: AbortSignal) =>
  apiRequest<AuthUser>('/auth/me', { token, signal })
