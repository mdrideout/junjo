import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ActionButton } from '../../components/actions/action-button'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import type { AgentExecutionSummary } from './schemas/agent-execution'
import { AgentExecutionQuerySchema, type AgentExecutionQuery } from './schemas/query'
import { AgentExecutionsActions } from './store/slice'
import { selectAgentExecutionListRequest } from './store/selectors'
import { formatNanoseconds, shortIdentity } from './utils/format'

const fieldClassName =
  'min-h-10 w-full rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 text-sm ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'

function queryFromSearchParams(parameters: URLSearchParams): AgentExecutionQuery | null {
  const serviceName = parameters.get('service_name') ?? ''
  if (!serviceName) return null

  const optional = (key: string) => parameters.get(key) || undefined
  const limitText = optional('limit')
  const parsed = AgentExecutionQuerySchema.safeParse({
    service_namespace: parameters.get('service_namespace') ?? '',
    service_name: serviceName,
    agent_key: optional('agent_key'),
    structural_id: optional('structural_id'),
    service_version: optional('service_version'),
    outcome: optional('outcome'),
    start_time: optional('start_time'),
    end_time: optional('end_time'),
    limit: limitText === undefined ? undefined : Number(limitText),
  })

  return parsed.success ? parsed.data : null
}

function AgentExecutionRow({ execution }: { execution: AgentExecutionSummary }) {
  const destination = `/agents/${execution.trace_id}/${execution.agent_span_id}`

  return (
    <tr className="border-b border-[var(--studio-border)] last:border-0 hover:bg-[var(--studio-surface-hover)]">
      <th scope="row" className="p-0 text-left">
        <Link to={destination} className="block px-3 py-3 font-semibold">
          {execution.agent_name}
          <span className="mt-1 block font-mono text-xs font-normal text-[var(--studio-text-subtle)]">
            {execution.agent_key}
          </span>
        </Link>
      </th>
      <td className="px-3 py-3">
        <span className={`agent-outcome-${execution.outcome} rounded-full px-2 py-1 text-xs font-semibold`}>
          {execution.outcome}
        </span>
        <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">{execution.termination_reason}</div>
      </td>
      <td className="px-3 py-3 font-mono text-xs">{execution.counts.model_requests} / {execution.limits.model_requests}</td>
      <td className="px-3 py-3 font-mono text-xs">
        {execution.counts.tool_calls.requested} / {execution.limits.tool_calls}
        <span className="mt-1 block text-[var(--studio-text-subtle)]">
          {execution.counts.tool_calls.completed} completed
        </span>
      </td>
      <td className="px-3 py-3 font-mono text-xs">{formatNanoseconds(execution.duration_ns)}</td>
      <td className="px-3 py-3 font-mono text-xs" title={execution.structural_id}>
        {shortIdentity(execution.structural_id)}
      </td>
      <td className="px-3 py-3 text-xs text-[var(--studio-text-muted)]">
        {new Date(execution.start_time).toLocaleString()}
      </td>
    </tr>
  )
}

export function AgentExecutionResults({ query }: { query: AgentExecutionQuery }) {
  const dispatch = useAppDispatch()
  const request = useAppSelector((state) => selectAgentExecutionListRequest(state, query))

  useEffect(() => {
    dispatch(AgentExecutionsActions.fetchAgentExecutions(query))
  }, [dispatch, query])

  if (request.loading && request.data.length === 0) {
    return <p className="text-sm text-[var(--studio-text-muted)]">Loading Agent executions…</p>
  }

  if (request.error !== null) {
    return (
      <div className="rounded-lg border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-4 text-sm">
        {request.error}
      </div>
    )
  }

  if (request.data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--studio-border-strong)] p-6 text-sm text-[var(--studio-text-muted)]">
        No Agent executions match this service scope and filter set.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
      <table className="w-full min-w-[68rem] text-left text-sm">
        <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
          <tr>
            <th scope="col" className="px-3 py-3">Agent</th>
            <th scope="col" className="px-3 py-3">Outcome</th>
            <th scope="col" className="px-3 py-3">Model</th>
            <th scope="col" className="px-3 py-3">Tools</th>
            <th scope="col" className="px-3 py-3">Duration</th>
            <th scope="col" className="px-3 py-3">Structure</th>
            <th scope="col" className="px-3 py-3">Started</th>
          </tr>
        </thead>
        <tbody>
          {request.data.map((execution) => (
            <AgentExecutionRow key={`${execution.trace_id}:${execution.agent_span_id}`} execution={execution} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AgentExecutionsPage() {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const query = useMemo(() => queryFromSearchParams(searchParameters), [searchParameters])
  const queryHasInvalidFilters = Boolean(searchParameters.get('service_name')) && query === null
  const [serviceNamespace, setServiceNamespace] = useState(searchParameters.get('service_namespace') ?? '')
  const [serviceName, setServiceName] = useState(searchParameters.get('service_name') ?? '')
  const [agentKey, setAgentKey] = useState(searchParameters.get('agent_key') ?? '')
  const [structuralId, setStructuralId] = useState(searchParameters.get('structural_id') ?? '')
  const [serviceVersion, setServiceVersion] = useState(searchParameters.get('service_version') ?? '')
  const [outcome, setOutcome] = useState(searchParameters.get('outcome') ?? '')
  const [startTime, setStartTime] = useState(searchParameters.get('start_time') ?? '')
  const [endTime, setEndTime] = useState(searchParameters.get('end_time') ?? '')

  useEffect(() => {
    setServiceNamespace(searchParameters.get('service_namespace') ?? '')
    setServiceName(searchParameters.get('service_name') ?? '')
    setAgentKey(searchParameters.get('agent_key') ?? '')
    setStructuralId(searchParameters.get('structural_id') ?? '')
    setServiceVersion(searchParameters.get('service_version') ?? '')
    setOutcome(searchParameters.get('outcome') ?? '')
    setStartTime(searchParameters.get('start_time') ?? '')
    setEndTime(searchParameters.get('end_time') ?? '')
  }, [searchParameters])

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const parameters = new URLSearchParams({
      service_namespace: serviceNamespace,
      service_name: serviceName.trim(),
      limit: '100',
    })
    if (agentKey.trim()) parameters.set('agent_key', agentKey.trim())
    if (structuralId.trim()) parameters.set('structural_id', structuralId.trim())
    if (serviceVersion.trim()) parameters.set('service_version', serviceVersion.trim())
    if (outcome) parameters.set('outcome', outcome)
    if (startTime.trim()) parameters.set('start_time', startTime.trim())
    if (endTime.trim()) parameters.set('end_time', endTime.trim())
    setSearchParameters(parameters)
  }

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <header>
        <h1 className="m-0 text-3xl">Agent executions</h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--studio-text-muted)]">
          Query realized Agent runs by their OpenTelemetry service scope. Studio presents backend-verified semantic evidence rather than inferring behavior from raw spans.
        </p>
      </header>

      <form onSubmit={submit} className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm font-medium">
            Service namespace
            <input
              className={`${fieldClassName} mt-1`}
              value={serviceNamespace}
              onChange={(event) => setServiceNamespace(event.target.value)}
              placeholder="Empty namespace"
            />
          </label>
          <label className="text-sm font-medium">
            Service name
            <input
              className={`${fieldClassName} mt-1`}
              value={serviceName}
              onChange={(event) => setServiceName(event.target.value)}
              required
              placeholder="my-ai-service"
            />
          </label>
          <label className="text-sm font-medium">
            Agent key
            <input
              className={`${fieldClassName} mt-1`}
              value={agentKey}
              onChange={(event) => setAgentKey(event.target.value)}
              placeholder="Optional"
            />
          </label>
          <label className="text-sm font-medium">
            Outcome
            <select className={`${fieldClassName} mt-1`} value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="">All outcomes</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
        </div>

        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-semibold">Structural and release filters</summary>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <label className="text-sm font-medium">
              Structural ID
              <input
                className={`${fieldClassName} mt-1 font-mono text-xs`}
                value={structuralId}
                onChange={(event) => setStructuralId(event.target.value)}
                placeholder="agent_sha256:…"
              />
            </label>
            <label className="text-sm font-medium">
              Service version
              <input
                className={`${fieldClassName} mt-1`}
                value={serviceVersion}
                onChange={(event) => setServiceVersion(event.target.value)}
                placeholder="Optional"
              />
            </label>
            <label className="text-sm font-medium">
              Started at or after
              <input
                className={`${fieldClassName} mt-1 font-mono text-xs`}
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
                placeholder="2026-07-14T12:00:00Z"
              />
            </label>
            <label className="text-sm font-medium">
              Ended at or before
              <input
                className={`${fieldClassName} mt-1 font-mono text-xs`}
                value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
                placeholder="2026-07-15T12:00:00Z"
              />
            </label>
          </div>
        </details>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <ActionButton type="submit">Query executions</ActionButton>
          {query !== null && <AppLink to="/agents">Clear filters</AppLink>}
        </div>
      </form>

      {query === null ? (
        <div className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-6 text-sm text-[var(--studio-text-muted)]">
          {queryHasInvalidFilters
            ? 'The URL contains an invalid Agent execution filter. Times must be ISO 8601 values with an explicit UTC offset.'
            : 'Enter a service name to query Agent evidence. An empty namespace is a valid, explicit service scope.'}
        </div>
      ) : (
        <AgentExecutionResults query={query} />
      )}
    </div>
  )
}
