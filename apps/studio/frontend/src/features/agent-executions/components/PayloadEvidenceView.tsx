import clsx from 'clsx'
import SpanAttributeKeyValueViewer from '../../../components/SpanAttributeKeyValueViewer'
import type { CandidateEvidence, PayloadEvidence } from '../schemas/agent-execution'

interface PayloadEvidenceViewProps {
  evidence: PayloadEvidence | null
  label: string
}

const modeLabels: Record<PayloadEvidence['mode'], string> = {
  full: 'Full',
  redacted: 'Redacted',
  excluded: 'Excluded',
  reference: 'Reference',
  missing: 'Missing',
}

export function PayloadEvidenceView({ evidence, label }: PayloadEvidenceViewProps) {
  if (evidence === null) {
    return (
      <section className="rounded-lg border border-dashed border-[var(--studio-border-strong)] p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">{label}</div>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">Not produced at this execution boundary.</p>
      </section>
    )
  }

  return (
    <section className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">{label}</div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={clsx(
              'rounded-full px-2 py-0.5 font-semibold',
              `agent-payload-mode-${evidence.mode}`,
            )}
          >
            {modeLabels[evidence.mode]}
          </span>
          {evidence.policy !== null && <span className="font-mono text-[var(--studio-text-subtle)]">{evidence.policy}</span>}
        </div>
      </div>

      {(evidence.mode === 'full' || evidence.mode === 'redacted') && (
        <div className="mt-3 max-h-80 overflow-auto rounded-md bg-[var(--studio-page)] p-3">
          <SpanAttributeKeyValueViewer value={evidence.value} />
        </div>
      )}

      {evidence.mode === 'excluded' && (
        <p className="mt-3 text-sm text-[var(--studio-text-muted)]">
          The declared telemetry policy intentionally excluded this payload.
        </p>
      )}

      {evidence.mode === 'reference' && (
        <div className="mt-3">
          <p className="text-sm text-[var(--studio-text-muted)]">
            This payload is represented by an opaque application reference. Studio does not resolve it automatically.
          </p>
          <code className="mt-2 block break-all rounded-md bg-[var(--studio-page)] p-2 text-xs">{evidence.reference}</code>
        </div>
      )}

      {evidence.mode === 'missing' && (
        <p className="mt-3 text-sm text-[var(--studio-evidence-partial-text)]">{evidence.reason}</p>
      )}
    </section>
  )
}

export function CandidateEvidenceView({ candidate, label }: { candidate: CandidateEvidence; label: string }) {
  if (!candidate.available) {
    return (
      <section className="rounded-lg border border-dashed border-[var(--studio-border-strong)] p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">{label}</div>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          Candidate unavailable: <span className="font-mono">{candidate.unavailable_reason}</span>
        </p>
      </section>
    )
  }

  return <PayloadEvidenceView evidence={candidate.payload} label={label} />
}
