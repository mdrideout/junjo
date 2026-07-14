import { AppLink } from '../../../components/navigation/app-link'
import SpanAttributeKeyValueViewer from '../../../components/SpanAttributeKeyValueViewer'
import type { AgentExecutionDetail, ParentExecutableReference } from '../schemas/agent-execution'
import { formatNanoseconds, formatUsageFieldName, shortIdentity } from '../utils/format'
import { AgentOperationTimeline } from './AgentOperationTimeline'
import { AgentStateTimeline } from './AgentStateTimeline'
import { EvidenceIntegrityBanner } from './EvidenceIntegrityBanner'
import { CandidateEvidenceView, PayloadEvidenceView } from './PayloadEvidenceView'

function ParentExecutableCard({ executable }: { executable: ParentExecutableReference }) {
  const destination = executable.executable_type === 'agent'
    ? `/agents/${executable.trace_id}/${executable.span_id}`
    : executable.executable_type === 'workflow' || executable.executable_type === 'subflow'
      ? `/workflows/${encodeURIComponent(executable.service.name)}/${executable.trace_id}/${executable.span_id}`
    : `/traces/${encodeURIComponent(executable.service.name)}/${executable.trace_id}/${executable.span_id}`

  return (
    <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">
            Semantic parent · {executable.executable_type}
          </div>
          <div className="mt-1 font-semibold">{executable.name}</div>
          <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
            {executable.service.namespace ? `${executable.service.namespace} / ` : ''}{executable.service.name}
          </div>
        </div>
        <AppLink to={destination}>Open parent diagnostics</AppLink>
      </div>
      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-[var(--studio-text-subtle)]">Runtime</dt>
          <dd className="font-mono" title={executable.runtime_id}>{shortIdentity(executable.runtime_id)}</dd>
        </div>
        <div>
          <dt className="text-[var(--studio-text-subtle)]">Semantic span</dt>
          <dd className="font-mono">{executable.span_id}</dd>
        </div>
        <div>
          <dt className="text-[var(--studio-text-subtle)]">Physical parent span</dt>
          <dd className="font-mono">{executable.physical_parent_span_id}</dd>
        </div>
      </dl>
    </section>
  )
}

function ExecutionTerminalEvidence({ detail }: { detail: AgentExecutionDetail }) {
  if (detail.error !== null) {
    return (
      <section className="rounded-xl border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-4">
        <h2 className="m-0 text-lg">Owning execution error</h2>
        <div className="mt-2 font-mono text-sm font-semibold">{detail.error.type}</div>
        {detail.error.message !== null && <p className="mt-2 whitespace-pre-wrap text-sm">{detail.error.message}</p>}
        {detail.error.stacktrace !== null && (
          <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-xs">{detail.error.stacktrace}</pre>
        )}
      </section>
    )
  }

  if (detail.cancellation !== null) {
    return (
      <section className="rounded-xl border border-[var(--studio-outcome-cancelled)] bg-[var(--studio-outcome-cancelled-bg)] p-4">
        <h2 className="m-0 text-lg">Execution cancelled</h2>
        <p className="mt-2 text-sm">{detail.cancellation.reason ?? 'No cancellation reason was supplied.'}</p>
      </section>
    )
  }

  return null
}

export function AgentExecutionDetailView({ detail }: { detail: AgentExecutionDetail }) {
  const { summary } = detail
  const listSearch = new URLSearchParams({
    service_namespace: summary.service.namespace,
    service_name: summary.service.name,
  })
  const rawTracePath = `/traces/${encodeURIComponent(summary.service.name)}/${summary.trace_id}/${summary.agent_span_id}`

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to={`/agents?${listSearch.toString()}`}>Agent executions</AppLink>
        <span aria-hidden="true">/</span>
        <span>{summary.agent_name}</span>
      </nav>

      <header className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-[var(--studio-text-muted)]">{summary.agent_key}</div>
            <h1 className="m-0 mt-1 text-3xl">{summary.agent_name}</h1>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-[var(--studio-text-subtle)]">
              <span>{summary.service.namespace ? `${summary.service.namespace} / ` : ''}{summary.service.name}</span>
              {summary.service.version !== null && <span>version {summary.service.version}</span>}
              <span title={summary.runtime_id}>run {shortIdentity(summary.runtime_id)}</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className={`agent-outcome-${summary.outcome} rounded-full px-3 py-1 text-sm font-bold`}>
              {summary.outcome}
            </span>
            <AppLink to={rawTracePath}>Raw trace</AppLink>
          </div>
        </div>

        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Termination</dt>
            <dd className="mt-1 font-mono text-sm">{summary.termination_reason}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Duration</dt>
            <dd className="mt-1 font-mono text-sm">{formatNanoseconds(summary.duration_ns)}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Model requests</dt>
            <dd className="mt-1 font-mono text-sm">{summary.counts.model_requests} / {summary.limits.model_requests}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Tool calls</dt>
            <dd className="mt-1 font-mono text-sm">
              {summary.counts.tool_calls.requested} requested / {summary.limits.tool_calls} limit
            </dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Operations</dt>
            <dd className="mt-1 font-mono text-sm">{summary.counts.operations}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Started</dt>
            <dd className="mt-1 text-xs">{new Date(summary.start_time).toLocaleString()}</dd>
          </div>
        </dl>

        <div className="mt-3 rounded-lg border border-[var(--studio-border)] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">Tool progression</div>
          <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(summary.counts.tool_calls).map(([name, count]) => (
              <div key={name}>
                <dt className="text-xs text-[var(--studio-text-subtle)]">{name}</dt>
                <dd className="font-mono text-sm font-semibold">{count}</dd>
              </div>
            ))}
          </dl>
        </div>

        <dl className="mt-3 grid gap-3 rounded-lg border border-[var(--studio-border)] p-3 text-xs lg:grid-cols-3">
          <div>
            <dt className="text-[var(--studio-text-subtle)]">Structural ID</dt>
            <dd className="mt-1 break-all font-mono">{summary.structural_id}</dd>
          </div>
          <div>
            <dt className="text-[var(--studio-text-subtle)]">Definition ID</dt>
            <dd className="mt-1 break-all font-mono">{summary.definition_id}</dd>
          </div>
          <div>
            <dt className="text-[var(--studio-text-subtle)]">Agent span</dt>
            <dd className="mt-1 break-all font-mono">{summary.agent_span_id}</dd>
          </div>
        </dl>
      </header>

      <EvidenceIntegrityBanner integrity={detail.integrity} />
      {detail.parent_executable !== null && (
        <ParentExecutableCard executable={detail.parent_executable} />
      )}
      <ExecutionTerminalEvidence detail={detail} />

      <section className="grid gap-4 xl:grid-cols-2">
        <PayloadEvidenceView evidence={detail.input} label="Validated application input" />
        <PayloadEvidenceView evidence={detail.output} label="Validated final output" />
        {detail.input_candidate !== null && (
          <CandidateEvidenceView candidate={detail.input_candidate} label="Rejected input candidate" />
        )}
        {detail.history_candidate !== null && (
          <CandidateEvidenceView candidate={detail.history_candidate} label="Rejected history candidate" />
        )}
      </section>

      <details className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
        <summary className="cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]">
          Agent definition and capabilities
        </summary>
        <div className="mt-4">
          <PayloadEvidenceView evidence={detail.definition} label="Definition snapshot" />
        </div>
      </details>

      <AgentOperationTimeline
        operations={detail.operations}
        nestedExecutables={detail.nested_executables}
      />
      <AgentStateTimeline state={detail.state} />

      <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
        <h2 className="m-0 text-lg">Usage evidence</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          {summary.usage.model_responses} normalized model response{summary.usage.model_responses === 1 ? '' : 's'} contributed usage facts.
        </p>
        {Object.keys(summary.usage.fields).length === 0 ? (
          <p className="mt-3 text-sm text-[var(--studio-text-muted)]">No provider usage fields were reported.</p>
        ) : (
          <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {Object.entries(summary.usage.fields).map(([name, observation]) => (
              <div key={name} className="rounded-lg bg-[var(--studio-surface-raised)] p-3">
                <dt className="text-xs capitalize text-[var(--studio-text-subtle)]">{formatUsageFieldName(name)}</dt>
                <dd className="mt-1 font-mono text-sm font-semibold">{observation.sum}</dd>
                <dd className="mt-1 text-xs text-[var(--studio-text-subtle)]">
                  {observation.observations} observation{observation.observations === 1 ? '' : 's'}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <details className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
        <summary className="cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]">
          Semantic API projection
        </summary>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          This is the backend-owned diagnostic model. Raw transport evidence remains available through the raw trace link.
        </p>
        <div className="mt-3 max-h-[36rem] overflow-auto rounded-lg bg-[var(--studio-page)] p-3">
          <SpanAttributeKeyValueViewer value={detail} />
        </div>
      </details>
    </div>
  )
}
