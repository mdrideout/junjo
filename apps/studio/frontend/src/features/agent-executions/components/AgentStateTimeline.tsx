import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import SpanAttributeKeyValueViewer from '../../../components/SpanAttributeKeyValueViewer'
import type { StoreDetail } from '../schemas/agent-execution'
import { PayloadEvidenceView } from './PayloadEvidenceView'

type StateSelection = { kind: 'start' } | { kind: 'transition'; sequence: number } | { kind: 'end' }

function StateProjection({ label, value, available }: { label: string; value: unknown; available: boolean }) {
  return (
    <section className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">{label}</div>
      {available ? (
        <div className="mt-3 max-h-80 overflow-auto rounded-md bg-[var(--studio-page)] p-3">
          <SpanAttributeKeyValueViewer value={value} />
        </div>
      ) : (
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          Backend replay did not produce this projection.
        </p>
      )}
    </section>
  )
}

export function AgentStateTimeline({ state }: { state: StoreDetail }) {
  const [selection, setSelection] = useState<StateSelection>({ kind: 'start' })
  const orderedTransitions = useMemo(
    () => [...state.transitions].sort((left, right) => left.sequence - right.sequence),
    [state.transitions],
  )

  useEffect(() => {
    setSelection({ kind: 'start' })
  }, [state.store_id])

  if (!state.available) {
    return (
      <section className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-5">
        <h2 className="m-0 text-lg">Agent state</h2>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          This invocation never admitted a run-local Store. No state or transition evidence is fabricated.
        </p>
        <p className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
          {state.reconstruction_reason}
        </p>
      </section>
    )
  }

  const selectedTransition = selection.kind === 'transition'
    ? orderedTransitions.find((transition) => transition.sequence === selection.sequence) ?? null
    : null

  return (
    <section aria-label="Agent state history" className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--studio-border)] p-4">
        <div>
          <h2 className="m-0 text-lg">Agent state revisions</h2>
          <p className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
            {state.store_id ?? 'Store identity unavailable'}
          </p>
          <p className="mt-1 text-xs text-[var(--studio-text-subtle)]">
            {state.transitions.length} of {state.transition_count} declared transition{state.transition_count === 1 ? '' : 's'} preserved
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={clsx(
              'rounded-full px-2.5 py-1 font-semibold',
              state.reconstruction_status === 'verified'
                ? 'bg-[var(--studio-evidence-complete-bg)] text-[var(--studio-evidence-complete-text)]'
                : 'bg-[var(--studio-evidence-partial-bg)] text-[var(--studio-evidence-partial-text)]',
            )}
          >
            {state.reconstruction_status === 'verified' && 'Backend replay verified'}
            {state.reconstruction_status === 'policy_unavailable' && 'Replay unavailable by payload policy'}
            {state.reconstruction_status === 'failed' && 'Replay verification failed'}
          </span>
          <span className="rounded-full bg-[var(--studio-page)] px-2.5 py-1 font-semibold text-[var(--studio-text-muted)]">
            Producer claim: {state.reconstructable_claimed ? 'reconstructable' : 'not reconstructable'}
          </span>
        </div>
      </div>

      {state.reconstruction_reason !== null && (
        <div className="border-b border-[var(--studio-border)] px-4 py-2 font-mono text-xs text-[var(--studio-text-muted)]">
          {state.reconstruction_reason}
        </div>
      )}

      <div className="grid min-h-[24rem] lg:grid-cols-[19rem_minmax(0,1fr)]">
        <ol className="m-0 list-none space-y-2 border-b border-[var(--studio-border)] p-3 lg:border-b-0 lg:border-r">
          <li className="m-0">
            <button
              type="button"
              aria-pressed={selection.kind === 'start'}
              onClick={() => setSelection({ kind: 'start' })}
              className={clsx(
                'w-full rounded-lg border p-3 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
                selection.kind === 'start'
                  ? 'border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)]'
                  : 'border-transparent hover:bg-[var(--studio-surface-hover)]',
              )}
            >
              <div className="font-semibold">Start</div>
              <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
                revision {state.revision_start ?? 'unavailable'}
              </div>
            </button>
          </li>

          {orderedTransitions.map((transition) => (
            <li key={transition.sequence} className="m-0">
              <button
                type="button"
                aria-pressed={selection.kind === 'transition' && selection.sequence === transition.sequence}
                onClick={() => setSelection({ kind: 'transition', sequence: transition.sequence })}
                className={clsx(
                  'w-full rounded-lg border p-3 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
                  selection.kind === 'transition' && selection.sequence === transition.sequence
                    ? 'border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)]'
                    : 'border-transparent hover:bg-[var(--studio-surface-hover)]',
                )}
              >
                <div className="font-semibold">{transition.sequence}. {transition.action}</div>
                <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
                  revision {transition.revision_before} → {transition.revision_after}
                </div>
              </button>
            </li>
          ))}

          <li className="m-0">
            <button
              type="button"
              aria-pressed={selection.kind === 'end'}
              onClick={() => setSelection({ kind: 'end' })}
              className={clsx(
                'w-full rounded-lg border p-3 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]',
                selection.kind === 'end'
                  ? 'border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)]'
                  : 'border-transparent hover:bg-[var(--studio-surface-hover)]',
              )}
            >
              <div className="font-semibold">End</div>
              <div className="mt-1 font-mono text-xs text-[var(--studio-text-subtle)]">
                revision {state.revision_end ?? 'unavailable'}
              </div>
            </button>
          </li>
        </ol>

        <div className="min-w-0 space-y-4 p-4 lg:p-5">
          {selection.kind === 'start' && <PayloadEvidenceView evidence={state.start} label="State start" />}
          {selection.kind === 'end' && <PayloadEvidenceView evidence={state.end} label="State end" />}
          {selectedTransition !== null && (
            <>
              <div className="flex flex-wrap justify-between gap-2 text-xs text-[var(--studio-text-subtle)]">
                <span className="font-mono">event {selectedTransition.event_id}</span>
                <span className="font-mono">owner span {selectedTransition.span_id}</span>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                <StateProjection
                  label="Before"
                  value={selectedTransition.before}
                  available={state.reconstructable && selectedTransition.before !== null}
                />
                <StateProjection
                  label="After"
                  value={selectedTransition.after}
                  available={state.reconstructable && selectedTransition.after !== null}
                />
              </div>
              <PayloadEvidenceView evidence={selectedTransition.patch} label="Emitted RFC 6902 patch" />
            </>
          )}
        </div>
      </div>
    </section>
  )
}
