import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { resolveExecution } from './fetch/resolve-execution'
import {
  ExecutionResolutionRequestSchema,
  type ExecutionResolution,
  type ExecutionResolutionRequest,
} from './schemas'
import { ResolvedExecutionDetail } from './ResolvedExecutionDetail'

const INITIAL_RESOLUTION_RETRY_DELAY_MS = 1_000
const MAX_RESOLUTION_RETRY_DELAY_MS = 5_000

function retryDelay(attempt: number): number {
  return Math.min(
    INITIAL_RESOLUTION_RETRY_DELAY_MS * 2 ** Math.min(attempt - 1, 3),
    MAX_RESOLUTION_RETRY_DELAY_MS,
  )
}

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
  const request = useMemo(() => requestFromSearch(location.search), [location.search])

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

  return <ExecutionResolver key={location.search} request={request} />
}

type ResolutionState =
  | { phase: 'resolving' }
  | { phase: 'pending' }
  | { phase: 'resolved'; resolution: ExecutionResolution }
  | { phase: 'failed'; message: string }

function ExecutionResolver({ request }: { request: ExecutionResolutionRequest }) {
  const [attempt, setAttempt] = useState(1)
  const [state, setState] = useState<ResolutionState>({ phase: 'resolving' })

  useEffect(() => {
    const controller = new AbortController()
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    void resolveExecution(request, controller.signal)
      .then((resolution) => {
        if (controller.signal.aborted) return
        if (resolution !== null) {
          setState({ phase: 'resolved', resolution })
          return
        }
        setState({ phase: 'pending' })
        retryTimer = setTimeout(
          () => setAttempt((current) => current + 1),
          retryDelay(attempt),
        )
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            phase: 'failed',
            message: reason instanceof Error ? reason.message : 'Execution resolution failed.',
          })
        }
      })

    return () => {
      controller.abort()
      if (retryTimer !== undefined) clearTimeout(retryTimer)
    }
  }, [attempt, request])

  if (state.phase === 'resolved') {
    return <ResolvedExecutionDetail request={request} resolution={state.resolution} />
  }

  return (
    <main className="px-4 py-3" aria-live="polite">
      <div className="mb-1 flex flex-wrap items-center gap-x-3 font-bold">
        <Link to="/logs" className="hover:underline">Logs</Link>
        <span aria-hidden="true">&rarr;</span>
        <span>{request.service_name}</span>
        <span aria-hidden="true">&rarr;</span>
        <h1 className="font-bold">
          {request.executable_type === 'agent' ? 'Agent execution' : 'Workflow execution'}
        </h1>
      </div>
      <div className="break-all font-mono text-xs text-[var(--studio-text-subtle)]">
        {request.runtime_id}
      </div>
      <hr className="my-4" />
      {state.phase === 'pending' ? (
        <section
          className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
          role="status"
        >
          <h2 className="font-semibold">Telemetry is still arriving</h2>
          <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
            Studio is waiting for this execution to be indexed. This page will update when its diagnostics are ready.
          </p>
        </section>
      ) : state.phase === 'failed' ? (
        <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-4" role="alert">
          <p className="font-medium text-red-900">Execution diagnostics could not be loaded.</p>
          <p className="mt-1 text-sm text-red-800">{state.message}</p>
        </div>
      ) : null}
    </main>
  )
}
