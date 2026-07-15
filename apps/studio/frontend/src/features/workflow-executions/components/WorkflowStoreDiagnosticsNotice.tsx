import type { WorkflowStoreDiagnostic } from '../schemas/workflow-store-diagnostic'

interface WorkflowStoreDiagnosticsNoticeProps {
  diagnostic: WorkflowStoreDiagnostic | null
  loading: boolean
  error: string | null
  ownerIdentified: boolean
}

function TechnicalDiagnostics({ diagnostic }: { diagnostic: WorkflowStoreDiagnostic }) {
  const diagnostics = diagnostic.integrity.diagnostics
  if (diagnostics.length === 0 && diagnostic.state.reconstruction_reason === null) return null

  return (
    <details className="mt-2">
      <summary className="cursor-pointer font-medium">Technical diagnostics</summary>
      <div className="mt-1 font-mono text-[var(--studio-text-muted)]">
        Store: {diagnostic.state.store_id ?? 'unavailable'}
      </div>
      {diagnostic.state.reconstruction_reason !== null && (
        <div className="mt-1 font-mono text-[var(--studio-text-muted)]">
          {diagnostic.state.reconstruction_reason}
        </div>
      )}
      {diagnostics.length > 0 && (
        <ul className="mt-2 space-y-1 pl-5">
          {diagnostics.map((item) => (
            <li key={`${item.code}:${item.path}`}>
              <span className="font-mono font-semibold">{item.code}</span>
              <span className="text-[var(--studio-text-subtle)]"> at {item.path}</span>
              <span>: {item.message}</span>
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}

export function WorkflowStoreDiagnosticsNotice({
  diagnostic,
  loading,
  error,
  ownerIdentified,
}: WorkflowStoreDiagnosticsNoticeProps) {
  if (loading) {
    return (
      <div
        className="border-t border-[var(--studio-border)] bg-[var(--studio-surface)] px-3 py-2 text-xs text-[var(--studio-text-muted)]"
        role="status"
      >
        Loading state history…
      </div>
    )
  }

  if (error !== null) {
    return (
      <div
        className="border-t border-red-300 bg-red-50 px-3 py-2 text-xs text-red-950 dark:border-red-900 dark:bg-red-950 dark:text-red-100"
        role="alert"
      >
        {error}
      </div>
    )
  }

  if (!ownerIdentified) {
    return (
      <div
        className="border-t border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
        role="alert"
      >
        Studio could not identify the Workflow or Subflow that owns this state history.
      </div>
    )
  }

  if (diagnostic === null) return null

  const reconstructionStatus = diagnostic.state.reconstruction_status
  const integrityComplete = diagnostic.integrity.status === 'complete'

  if (
    (reconstructionStatus === 'verified' && integrityComplete)
    || reconstructionStatus === 'not_applicable'
  ) {
    return null
  }

  const failed = reconstructionStatus === 'failed'
  const title = failed
    ? 'State history could not be verified'
    : reconstructionStatus === 'policy_unavailable'
      ? 'State history is unavailable by payload policy'
      : 'Telemetry for this state history is incomplete'
  const message = failed
    ? 'Studio preserved the raw spans and events, but reconstructed state views are disabled because the received Store history is inconsistent.'
    : reconstructionStatus === 'policy_unavailable'
      ? 'The configured payload policy withheld content required to reconstruct state. This does not indicate execution failure or telemetry corruption.'
      : 'Studio received enough data to show this execution, but some expected telemetry is missing or inconsistent.'

  return (
    <section
      aria-label="Workflow Store diagnostics"
      className={failed
        ? 'border-t border-red-300 bg-red-50 px-3 py-2 text-xs text-red-950 dark:border-red-900 dark:bg-red-950 dark:text-red-100'
        : 'border-t border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100'}
      role={failed ? 'alert' : 'status'}
    >
      <div className="font-semibold">{title}</div>
      <p className="mt-1">{message}</p>
      <TechnicalDiagnostics diagnostic={diagnostic} />
    </section>
  )
}
