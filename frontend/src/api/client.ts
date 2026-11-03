const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

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
  method?: 'GET' | 'POST'
  body?: unknown
  token?: string | null
  params?: Record<string, string | number | undefined>
  signal?: AbortSignal
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
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
