import clsx from 'clsx'
import type { WorkflowStoreDiagnostic } from '../schemas/workflow-store-diagnostic'

interface WorkflowStoreEvidenceBannerProps {
  diagnostic: WorkflowStoreDiagnostic | null
  loading: boolean
  error: string | null
  ownerIdentified: boolean
}

export function WorkflowStoreEvidenceBanner({
  diagnostic,
  loading,
  error,
  ownerIdentified,
}: WorkflowStoreEvidenceBannerProps) {
  if (!ownerIdentified) {
    return (
      <div className="border-t border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
        Studio could not identify the Workflow or Subflow that owns the active Store.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="border-t border-[var(--studio-border)] bg-[var(--studio-surface)] px-3 py-2 text-xs text-[var(--studio-text-muted)]">
        Verifying Workflow Store evidence in the backend…
      </div>
    )
  }

  if (error !== null) {
    return (
      <div className="border-t border-red-300 bg-red-50 px-3 py-2 text-xs text-red-950 dark:border-red-900 dark:bg-red-950 dark:text-red-100">
        {error}
      </div>
    )
  }

  if (diagnostic === null) return null

  const reconstructionStatus = diagnostic.state.reconstruction_status
  const verified = reconstructionStatus === 'verified'
  const complete = diagnostic.integrity.status === 'complete'
  const diagnostics = diagnostic.integrity.diagnostics
  const statusLabel = {
    verified: 'Backend Store replay verified',
    policy_unavailable: 'Backend Store replay unavailable by payload policy',
    failed: 'Backend Store replay verification failed',
    not_applicable: 'Store reconstruction is not applicable',
  }[reconstructionStatus]

  return (
    <section
      aria-label="Workflow Store evidence"
      className={clsx(
        'border-t px-3 py-2 text-xs',
        reconstructionStatus === 'failed'
          ? 'border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950'
          : verified && complete
            ? 'border-[var(--studio-evidence-complete)] bg-[var(--studio-evidence-complete-bg)]'
            : 'border-[var(--studio-evidence-partial)] bg-[var(--studio-evidence-partial-bg)]',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold">
          {statusLabel}
        </span>
        <span className="font-mono text-[var(--studio-text-subtle)]">
          {diagnostic.executable_type} · {diagnostic.state.store_id ?? 'Store unavailable'} · evidence {diagnostic.integrity.status}
        </span>
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
    </section>
  )
}
