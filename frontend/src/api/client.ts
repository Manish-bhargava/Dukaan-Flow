export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

/** Standard success envelope (docs/API_DESIGN.MD). */
export interface ApiResponse<T> {
  success: true
  message: string
  data: T
}

/** A failed request, carrying the backend's standard error envelope. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(message: string, status: number, code: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  token?: string | null
  params?: Record<string, string | number | string[] | undefined>
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(options.params ?? {})) {
    for (const v of Array.isArray(value) ? value : [value]) {
      if (v !== undefined && v !== '') url.searchParams.append(key, String(v))
    }
  }

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.token) headers.Authorization = `Bearer ${options.token}`

  let response: Response
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError('Cannot reach the DukaanFlow server. Check your connection and try again.', 0, 'NETWORK_ERROR')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.success) {
    throw new ApiError(
      payload?.message ?? `Request failed (HTTP ${response.status})`,
      response.status,
      payload?.error_code ?? 'UNKNOWN_ERROR',
      payload?.details ?? {},
    )
  }
  return payload as ApiResponse<T>
}

/** Download a file (e.g. CSV) from an authenticated endpoint. */
export async function apiDownload(
  path: string,
  token: string,
  params: Record<string, string | undefined> = {},
  body?: unknown,
): Promise<{ blob: Blob; filename: string; headers: Headers }> {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(params)) if (value) url.searchParams.set(key, value)
  let response: Response
  try {
    response = await fetch(url, body === undefined
      ? { headers: { Authorization: `Bearer ${token}` } }
      : { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch {
    throw new ApiError('Cannot reach the DukaanFlow server. Check your connection and try again.', 0, 'NETWORK_ERROR')
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(payload?.message ?? `Download failed (HTTP ${response.status})`, response.status, payload?.error_code ?? 'UNKNOWN_ERROR', payload?.details ?? {})
  }
  const disposition = response.headers.get('content-disposition') ?? ''
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'download.csv'
  return { blob: await response.blob(), filename, headers: response.headers }
}
