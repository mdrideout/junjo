import clsx from 'clsx'
import type { EvidenceIntegrity } from '../schemas/agent-execution'

export function EvidenceIntegrityBanner({ integrity }: { integrity: EvidenceIntegrity }) {
  const losses = Object.entries(integrity.loss_counts).filter(([, count]) => count > 0)
  const complete = integrity.status === 'complete'

  return (
    <section
      aria-label="Evidence integrity"
      className={clsx(
        'rounded-xl border p-4',
        complete
          ? 'border-[var(--studio-evidence-complete)] bg-[var(--studio-evidence-complete-bg)]'
          : 'border-[var(--studio-evidence-partial)] bg-[var(--studio-evidence-partial-bg)]',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="m-0 text-base">Contract evidence: {complete ? 'complete' : 'partial'}</h2>
          <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
            {complete
              ? 'Required Agent evidence reconciles; any claimed Store reconstruction was backend-verified.'
              : 'Diagnostics below identify missing, inconsistent, or dropped contract evidence.'}
          </p>
        </div>
        <span
          className={clsx(
            'rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide',
            complete
              ? 'bg-[var(--studio-evidence-complete)] text-white'
              : 'bg-[var(--studio-evidence-partial)] text-[var(--studio-evidence-partial-contrast)]',
          )}
        >
          {integrity.status}
        </span>
      </div>

      {!complete && integrity.diagnostics.length > 0 && (
        <ul className="mt-3 space-y-2 pl-5 text-sm">
          {integrity.diagnostics.map((diagnostic) => (
            <li key={`${diagnostic.code}:${diagnostic.path}`}>
              <span className="font-mono font-semibold">{diagnostic.code}</span>
              <span className="text-[var(--studio-text-subtle)]"> at {diagnostic.path}</span>
              <div>{diagnostic.message}</div>
            </li>
          ))}
        </ul>
      )}

      {losses.length > 0 && (
        <div className="mt-3 border-t border-current/20 pt-3">
          <div className="text-xs font-semibold uppercase tracking-wide">Preserved OTLP loss signals</div>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {losses.map(([name, count]) => (
              <div key={name}>
                <dt className="text-xs text-[var(--studio-text-subtle)]">{name.split('_').join(' ')}</dt>
                <dd className="font-mono text-sm font-semibold">{count}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  )
}
