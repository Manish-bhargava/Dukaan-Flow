import { apiRequest } from './client'
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
}

export interface Extraction {
  extraction_id: string
  status: string
  original_message: string
  model_name: string | null
  items: ExtractionItem[]
}

export const extractOrder = (token: string, message: string) =>
  apiRequest<Extraction>('/ai-orders/extract', { method: 'POST', token, body: { message } })

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
