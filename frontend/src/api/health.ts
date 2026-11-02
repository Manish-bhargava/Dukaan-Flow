const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

export interface HealthData {
  status: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<ApiResponse<HealthData>> {
  const response = await fetch(`${API_BASE_URL}/health`, { signal })
  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`)
  }
  return response.json()
}
