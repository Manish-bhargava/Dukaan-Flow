import { API_BASE_URL, ApiError, apiRequest } from './client'
import type { Order } from './orders'

export interface ProductChoice {
  product_id: string
  sku: string
  name: string
  pack_size: string
  order_unit?: string
}

export interface ExtractionItem {
  id: string
  original_text: string
  extracted_name: string
  quantity: string | null
  unit: string | null
  product: (ProductChoice & { order_unit: string }) | null
  confidence: string
  alternatives: (ProductChoice & { confidence: number })[]
  requires_clarification: boolean
  clarification: string | null
  evidence: string[] // why the AI chose this product (business evidence)
}

export interface Extraction {
  extraction_id: string
  status: string
  input_type: 'TEXT' | 'IMAGE' | 'VOICE'
  original_message: string
  model_name: string | null
  items: ExtractionItem[]
}

export interface DraftSummary {
  extraction_id: string
  created_at: string
  original_message: string
  item_count: number
  needs_clarification: boolean
}

/** AI drafts the retailer has not placed as orders yet. */
export const listDrafts = (token: string, signal?: AbortSignal) => apiRequest<DraftSummary[]>('/ai-orders', { token, signal })

export const getExtraction = (token: string, id: string, signal?: AbortSignal) =>
  apiRequest<Extraction>(`/ai-orders/${id}`, { token, signal })

export const extractOrder = (token: string, message: string) =>
  apiRequest<Extraction>('/ai-orders/extract', { method: 'POST', token, body: { message } })

/** A photo of an order list or a voice note -> draft (multipart upload). */
export async function extractMedia(token: string, kind: 'image' | 'voice', file: Blob, filename: string) {
  const body = new FormData()
  body.append('kind', kind)
  body.append('file', file, filename)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/ai-orders/extract-media`, { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body })
  } catch {
    throw new ApiError('Cannot reach the DukaanFlow server. Check your connection and try again.', 0, 'NETWORK_ERROR')
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(payload?.message ?? `Request failed (HTTP ${response.status})`, response.status, payload?.error_code ?? 'UNKNOWN_ERROR', payload?.details ?? {})
  }
  return payload as { data: Extraction; message: string }
}

export const confirmExtraction = (
  token: string,
  extractionId: string,
  items: { extraction_item_id: string | null; product_id: string; quantity: number; unit: string }[],
  remarks?: string,
) =>
  apiRequest<Order>(`/ai-orders/${extractionId}/confirm`, {
    method: 'POST',
    token,
    body: { items, remarks: remarks || null },
  })
