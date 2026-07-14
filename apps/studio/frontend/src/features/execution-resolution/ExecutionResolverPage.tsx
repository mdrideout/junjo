import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { resolveExecution } from './fetch/resolve-execution'
import {
  ExecutionResolutionRequestSchema,
  type ExecutionResolutionRequest,
} from './schemas'

const MAX_RESOLUTION_ATTEMPTS = 15
const RESOLUTION_RETRY_DELAY_MS = 1000

function requestFromSearch(search: string): ExecutionResolutionRequest | null {
  const parameters = new URLSearchParams(search)
  const parsed = ExecutionResolutionRequestSchema.safeParse({
    service_namespace: parameters.get('service_namespace'),
    service_name: parameters.get('service_name'),
    executable_type: parameters.get('executable_type'),
    runtime_id: parameters.get('runtime_id'),
    destination: parameters.get('destination'),
  })
  return parsed.success ? parsed.data : null
}

export default function ExecutionResolverPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const request = useMemo(() => requestFromSearch(location.search), [location.search])
  const [attempt, setAttempt] = useState(1)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setAttempt(1)
    setError(null)
  }, [request])

  useEffect(() => {
    if (request === null || error !== null) return
    const controller = new AbortController()
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    void resolveExecution(request, controller.signal)
      .then((resolution) => {
        if (controller.signal.aborted) return
        if (resolution !== null) {
          navigate(
            request.destination === 'trace'
              ? resolution.trace_path
              : resolution.detail_path,
            { replace: true },
          )
          return
        }
        if (attempt >= MAX_RESOLUTION_ATTEMPTS) {
          setError('Studio did not receive this execution before the resolution window ended.')
          return
        }
        retryTimer = setTimeout(() => setAttempt((current) => current + 1), RESOLUTION_RETRY_DELAY_MS)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : 'Execution resolution failed.')
        }
      })

    return () => {
      controller.abort()
      if (retryTimer !== undefined) clearTimeout(retryTimer)
    }
  }, [attempt, error, navigate, request])

  if (request === null) {
    return (
      <main className="mx-auto max-w-2xl p-8" role="alert">
        <h1 className="text-xl font-semibold">Invalid execution link</h1>
        <p className="mt-2 text-sm text-zinc-600">
          The link must identify a service, executable type, runtime ID, and destination.
        </p>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-2xl p-8" aria-live="polite">
      <h1 className="text-xl font-semibold">Resolving execution evidence</h1>
      {error === null ? (
        <p className="mt-2 text-sm text-zinc-600">
          Waiting for telemetry from <strong>{request.service_name}</strong>… attempt {attempt} of{' '}
          {MAX_RESOLUTION_ATTEMPTS}
        </p>
      ) : (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4" role="alert">
          <p className="font-medium text-red-900">Execution evidence could not be resolved.</p>
          <p className="mt-1 text-sm text-red-800">{error}</p>
          <p className="mt-3 break-all font-mono text-xs text-red-700">
            {request.executable_type}: {request.runtime_id}
          </p>
        </div>
      )}
    </main>
  )
}
