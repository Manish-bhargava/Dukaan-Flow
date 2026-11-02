import { useEffect, useState } from 'react'
import { fetchHealth } from './api/health'

type ConnectionStatus =
  | { state: 'checking' }
  | { state: 'connected'; message: string }
  | { state: 'error'; message: string }

const statusStyles: Record<ConnectionStatus['state'], string> = {
  checking: 'bg-amber-50 text-amber-800 ring-amber-200',
  connected: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  error: 'bg-red-50 text-red-800 ring-red-200',
}

const statusLabels: Record<ConnectionStatus['state'], string> = {
  checking: 'Checking backend connection…',
  connected: 'Backend connected',
  error: 'Backend unreachable',
}

function App() {
  const [status, setStatus] = useState<ConnectionStatus>({ state: 'checking' })

  useEffect(() => {
    const controller = new AbortController()

    fetchHealth(controller.signal)
      .then((res) => setStatus({ state: 'connected', message: res.message }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setStatus({
          state: 'error',
          message: err instanceof Error ? err.message : 'Unknown error',
        })
      })

    return () => controller.abort()
  }, [])

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
        <h1 className="text-3xl font-bold text-slate-900">DukaanFlow</h1>
        <p className="mt-2 text-slate-600">
          FMCG distribution and retailer ordering platform with AI-assisted order capture.
        </p>

        <div className={`mt-6 rounded-lg p-4 ring-1 ${statusStyles[status.state]}`}>
          <p className="font-medium">{statusLabels[status.state]}</p>
          {status.state !== 'checking' && <p className="mt-1 text-sm">{status.message}</p>}
        </div>
      </div>
    </main>
  )
}

export default App
