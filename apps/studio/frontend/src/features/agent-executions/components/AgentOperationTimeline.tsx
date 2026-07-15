import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import SpanAttributeKeyValueViewer from '../../../components/SpanAttributeKeyValueViewer'
import { AppLink } from '../../../components/navigation/app-link'
import type {
  AgentOperation,
  ModelOperation,
  NestedExecutableReference,
  ToolOperation,
} from '../schemas/agent-execution'
import { formatNanoseconds } from '../utils/format'
import { CandidateEvidenceView, PayloadEvidenceView } from './PayloadEvidenceView'

function OperationOutcome({ outcome }: { outcome: AgentOperation['outcome'] }) {
  return <span className={`agent-outcome-${outcome} rounded-full px-2 py-0.5 text-xs font-semibold`}>{outcome}</span>
}

function OperationFailure({ operation }: { operation: AgentOperation }) {
  if (operation.error !== null) {
    return (
      <section className="rounded-lg border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-3">
        <div className="text-sm font-semibold">{operation.error.type}</div>
        {operation.error.message !== null && <p className="mt-1 whitespace-pre-wrap text-sm">{operation.error.message}</p>}
        {operation.error.stacktrace !== null && (
          <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{operation.error.stacktrace}</pre>
        )}
      </section>
    )
  }

  if (operation.cancellation !== null) {
    return (
      <section className="rounded-lg border border-[var(--studio-outcome-cancelled)] bg-[var(--studio-outcome-cancelled-bg)] p-3 text-sm">
        Cancelled{operation.cancellation.reason === null ? '' : `: ${operation.cancellation.reason}`}
      </section>
    )
  }

  return null
}

function ModelOperationInspector({ operation }: { operation: ModelOperation }) {
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-operation-model)]">
            Model request {operation.ordinal}
          </div>
          <h3 className="m-0 mt-1 text-lg">{operation.provider} / {operation.model_name}</h3>
          <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
            {operation.driver_key} · state revision {operation.state_revision}
          </div>
        </div>
        <OperationOutcome outcome={operation.outcome} />
      </header>

      <OperationFailure operation={operation} />

      <PayloadEvidenceView evidence={operation.request} label="Normalized request" />

      <div className="grid gap-4 xl:grid-cols-2">
        <CandidateEvidenceView candidate={operation.response_candidate} label="Returned candidate" />
        <PayloadEvidenceView evidence={operation.response} label="Validated response" />
      </div>

      {operation.requested_tool_calls.length > 0 && (
        <section className="rounded-lg border border-[var(--studio-border)] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">
            Tool calls requested by this response
          </div>
          <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
            Requests that were admitted appear separately in the realized operation sequence. Rejected requests stay here as model-response evidence.
          </p>
          <ol className="mt-3 list-none space-y-2 p-0">
            {operation.requested_tool_calls.map((toolCall) => (
              <li key={toolCall.call_id} className="m-0 rounded-md bg-[var(--studio-page)] p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">{toolCall.tool_name}</div>
                    <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
                      request {toolCall.ordinal} · {toolCall.call_id}
                    </div>
                  </div>
                  <span
                    className={clsx(
                      'rounded-full px-2.5 py-1 text-xs font-semibold',
                      toolCall.admission === 'admitted' && toolCall.observed_tool_operation
                        ? 'bg-[var(--studio-evidence-complete-bg)] text-[var(--studio-evidence-complete-text)]'
                        : 'bg-[var(--studio-evidence-partial-bg)] text-[var(--studio-evidence-partial-text)]',
                    )}
                  >
                    {toolCall.admission === 'admitted' && toolCall.observed_tool_operation && 'admitted · operation observed'}
                    {toolCall.admission === 'admitted' && !toolCall.observed_tool_operation && 'admitted · execution interrupted'}
                    {toolCall.admission === 'not_admitted' && 'not admitted'}
                    {toolCall.admission === 'unknown' && 'admission unknown'}
                  </span>
                </div>
                <div className="mt-2 text-xs text-[var(--studio-text-muted)]">
                  {toolCall.observed_tool_operation
                    ? 'A realized Tool operation was observed for this request.'
                    : 'No Tool operation began for this request.'}
                </div>
                {toolCall.reason !== null && (
                  <div className="mt-1 text-sm">{toolCall.reason.replace(/_/g, ' ')}</div>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="rounded-lg border border-[var(--studio-border)] p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">Response facts</div>
        <dl className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Response type</dt>
            <dd className="font-mono text-sm">{operation.response_type ?? 'not validated'}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Duration</dt>
            <dd className="font-mono text-sm">{formatNanoseconds(operation.duration_ns)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Started</dt>
            <dd className="text-xs">{new Date(operation.start_time).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Span</dt>
            <dd className="font-mono text-xs">{operation.span_id}</dd>
          </div>
        </dl>
        {operation.usage !== null && (
          <div className="mt-3 rounded-md bg-[var(--studio-page)] p-3">
            <SpanAttributeKeyValueViewer value={operation.usage} />
          </div>
        )}
      </section>
    </div>
  )
}

function NestedExecutableCard({ executable }: { executable: NestedExecutableReference }) {
  const destination = executable.executable_type === 'workflow'
    ? `/workflows/${encodeURIComponent(executable.service.name)}/${executable.trace_id}/${executable.span_id}`
    : `/agents/${executable.trace_id}/${executable.span_id}`

  return (
    <li className="m-0 rounded-md bg-[var(--studio-page)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-operation-workflow)]">
            Nested {executable.executable_type}
          </div>
          <div className="mt-1 font-semibold">{executable.name}</div>
          <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
            span {executable.span_id}
          </div>
        </div>
        <AppLink to={destination}>Open diagnostics</AppLink>
      </div>
      <div className="mt-2 font-mono text-xs text-[var(--studio-text-subtle)]">
        Physical owner: Tool operation {executable.parent_operation_sequence} · {executable.parent_operation_span_id}
      </div>
    </li>
  )
}

function ToolOperationInspector({
  operation,
  nestedExecutables,
}: {
  operation: ToolOperation
  nestedExecutables: NestedExecutableReference[]
}) {
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-operation-tool)]">
            Tool call {operation.ordinal}
          </div>
          <h3 className="m-0 mt-1 text-lg">{operation.tool_name}</h3>
          <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
            {operation.call_id} · revision {operation.state_revision_before}
            {operation.state_revision_after === null ? '' : ` → ${operation.state_revision_after}`}
          </div>
        </div>
        <OperationOutcome outcome={operation.outcome} />
      </header>

      <OperationFailure operation={operation} />

      <div className="grid gap-4 xl:grid-cols-2">
        <PayloadEvidenceView evidence={operation.requested_arguments} label="Requested arguments" />
        <PayloadEvidenceView evidence={operation.arguments} label="Validated arguments" />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <CandidateEvidenceView candidate={operation.result_candidate} label="Returned candidate" />
        <PayloadEvidenceView evidence={operation.result} label="Validated result" />
      </div>

      {nestedExecutables.length > 0 && (
        <section className="rounded-lg border border-[var(--studio-border)] p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">
            Child executables invoked by this Tool
          </div>
          <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
            Each child owns its own state and diagnostics. The Tool span is its physical parent.
          </p>
          <ul className="mt-3 list-none space-y-2 p-0">
            {nestedExecutables.map((executable) => (
              <NestedExecutableCard
                key={`${executable.trace_id}:${executable.span_id}`}
                executable={executable}
              />
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border border-[var(--studio-border)] p-3">
        <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Tool structural ID</dt>
            <dd className="break-all font-mono text-xs">{operation.tool_structural_id}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Duration</dt>
            <dd className="font-mono text-sm">{formatNanoseconds(operation.duration_ns)}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Started</dt>
            <dd className="text-xs">{new Date(operation.start_time).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--studio-text-subtle)]">Span</dt>
            <dd className="font-mono text-xs">{operation.span_id}</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}

export function AgentOperationTimeline({
  operations,
  nestedExecutables,
}: {
  operations: AgentOperation[]
  nestedExecutables: NestedExecutableReference[]
}) {
  const orderedOperations = useMemo(
    () => [...operations].sort((left, right) => left.sequence - right.sequence),
    [operations],
  )
  const [selectedSequence, setSelectedSequence] = useState<number | null>(orderedOperations[0]?.sequence ?? null)

  useEffect(() => {
    setSelectedSequence(orderedOperations[0]?.sequence ?? null)
  }, [orderedOperations])

  const selected = orderedOperations.find((operation) => operation.sequence === selectedSequence) ?? null

  if (operations.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-5">
        <h2 className="m-0 text-lg">Realized operation sequence</h2>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          No model or Tool operation began. Boundary validation may have rejected this invocation.
        </p>
      </section>
    )
  }

  return (
    <section aria-label="Realized Agent operations" className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)]">
      <div className="border-b border-[var(--studio-border)] p-4">
        <h2 className="m-0 text-lg">Realized operation sequence</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Sequence numbers are authoritative; timestamps are display evidence only.
        </p>
      </div>

      <div className="grid min-h-[34rem] lg:grid-cols-[19rem_minmax(0,1fr)]">
        <ol className="m-0 list-none space-y-2 border-b border-[var(--studio-border)] p-3 lg:border-b-0 lg:border-r">
          {orderedOperations.map((operation) => {
            const isSelected = operation.sequence === selectedSequence
            const title = operation.operation_type === 'model_request'
              ? `${operation.provider} / ${operation.model_name}`
              : operation.tool_name

            return (
              <li key={operation.sequence} className="m-0">
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => setSelectedSequence(operation.sequence)}
                  className={clsx(
                    'w-full rounded-lg border p-3 text-left transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
                    isSelected
                      ? 'border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] shadow-sm'
                      : 'border-transparent hover:bg-[var(--studio-surface-hover)]',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={clsx(
                        'text-xs font-bold uppercase tracking-wide',
                        operation.operation_type === 'model_request'
                          ? 'text-[var(--studio-operation-model)]'
                          : 'text-[var(--studio-operation-tool)]',
                      )}
                    >
                      {operation.sequence}. {operation.operation_type === 'model_request' ? 'Model' : 'Tool'}
                    </span>
                    <OperationOutcome outcome={operation.outcome} />
                  </div>
                  <div className="mt-2 truncate text-sm font-semibold" title={title}>{title}</div>
                  <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
                    {formatNanoseconds(operation.duration_ns)}
                  </div>
                </button>
              </li>
            )
          })}
        </ol>

        <div className="min-w-0 p-4 lg:p-5">
          {selected?.operation_type === 'model_request' && <ModelOperationInspector operation={selected} />}
          {selected?.operation_type === 'tool' && (
            <ToolOperationInspector
              operation={selected}
              nestedExecutables={nestedExecutables.filter(
                (executable) =>
                  executable.parent_operation_sequence === selected.sequence &&
                  executable.parent_operation_span_id === selected.span_id,
              )}
            />
          )}
        </div>
      </div>
    </section>
  )
}
