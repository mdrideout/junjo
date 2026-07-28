import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import { SemanticExecutionLink } from './components/SemanticExecutionLink'
import { evaluationRunComparisonQueryFromSearchParams } from './schemas/query'
import {
  selectEvaluationRunComparison,
  selectEvaluationRunDetailRequest,
} from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

const EMPTY_COMPARISON_QUERY = {
  baseline_run_id: '',
  candidate_run_id: '',
}

function displayScore(score: number | null): string {
  return score === null ? '—' : score.toFixed(2)
}

function displayScoreDelta(delta: number | null): string {
  if (delta === null) return '—'
  return `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`
}

function displayDuration(durationMs: number | null): string {
  return durationMs === null ? '—' : `${durationMs} ms`
}

function displayDurationDelta(deltaMs: number | null): string {
  if (deltaMs === null) return '—'
  return `${deltaMs > 0 ? '+' : ''}${deltaMs} ms`
}

export default function EvaluationRunComparisonPage() {
  const [searchParameters] = useSearchParams()
  const query = useMemo(
    () => evaluationRunComparisonQueryFromSearchParams(searchParameters),
    [searchParameters],
  )
  const baselineRunId = query?.baseline_run_id ?? ''
  const candidateRunId = query?.candidate_run_id ?? ''
  const dispatch = useAppDispatch()
  const baselineRequest = useAppSelector((state) =>
    selectEvaluationRunDetailRequest(state, baselineRunId),
  )
  const candidateRequest = useAppSelector((state) =>
    selectEvaluationRunDetailRequest(state, candidateRunId),
  )
  const comparison = useAppSelector((state) =>
    selectEvaluationRunComparison(state, query ?? EMPTY_COMPARISON_QUERY),
  )

  useEffect(() => {
    if (query === null) return
    dispatch(EvaluationRunsActions.fetchEvaluationRun(query.baseline_run_id))
    dispatch(EvaluationRunsActions.fetchEvaluationRun(query.candidate_run_id))
  }, [dispatch, query])

  if (query === null) {
    return (
      <ErrorPage
        title="Invalid evaluation comparison"
        message="Two different, non-empty baseline and candidate run IDs are required."
      />
    )
  }

  if (
    (baselineRequest.loading && baselineRequest.data === null)
    || (candidateRequest.loading && candidateRequest.data === null)
    || (baselineRequest.data === null && baselineRequest.error === null)
    || (candidateRequest.data === null && candidateRequest.error === null)
  ) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">Loading evaluation comparison…</div>
  }
  if (baselineRequest.error !== null || candidateRequest.error !== null) {
    return (
      <ErrorPage
        title="Evaluation comparison unavailable"
        message={baselineRequest.error ?? candidateRequest.error ?? 'Failed to load comparison runs.'}
      />
    )
  }
  if (comparison.error !== null) {
    return <ErrorPage title="Evaluation runs are not comparable" message={comparison.error} />
  }
  if (comparison.data === null) {
    return <ErrorPage title="Evaluation comparison unavailable" message="Run details were not available." />
  }

  const { baseline_run: baseline, candidate_run: candidate, dataset, rows } = comparison.data
  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to="/evaluation-runs">Evaluation runs</AppLink>
        <span aria-hidden="true">/</span>
        <span>Comparison</span>
      </nav>

      <header>
        <h1 className="m-0 text-3xl">Baseline and candidate</h1>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          {dataset.name} · {dataset.key}
        </p>
      </header>

      <section className="grid gap-4 lg:grid-cols-2" aria-label="Compared runs">
        {[
          { role: 'Baseline', run: baseline },
          { role: 'Candidate', run: candidate },
        ].map(({ role, run }) => (
          <article
            key={run.id}
            className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">
                  {role}
                </div>
                <h2 className="m-0 mt-1 text-xl">{run.candidate_label}</h2>
              </div>
              <EvaluationStatusBadge status={run.status} />
            </div>
            <dl className="mt-3 space-y-2 text-xs">
              <div>
                <dt className="text-[var(--studio-text-subtle)]">Run</dt>
                <dd className="break-all font-mono">{run.id}</dd>
              </div>
              <div>
                <dt className="text-[var(--studio-text-subtle)]">Source revision</dt>
                <dd className="break-all font-mono">{run.source_revision}</dd>
              </div>
            </dl>
            <div className="mt-3">
              <AppLink to={`/evaluation-runs/${encodeURIComponent(run.id)}`}>Open run detail</AppLink>
            </div>
          </article>
        ))}
      </section>

      <section>
        <h2 className="m-0 text-xl">Case-by-case delta</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Score and duration deltas are candidate minus baseline. Reasons remain side by side as evaluator evidence.
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
          <table className="w-full min-w-[88rem] text-left text-sm">
            <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
              <tr>
                <th scope="col" className="px-3 py-3">Case</th>
                <th scope="col" className="px-3 py-3">Pass/status</th>
                <th scope="col" className="px-3 py-3">Score</th>
                <th scope="col" className="px-3 py-3">Reason</th>
                <th scope="col" className="px-3 py-3">Duration</th>
                <th scope="col" className="px-3 py-3">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.case.id} className="border-b border-[var(--studio-border)] last:border-0 align-top">
                  <th scope="row" className="px-3 py-3 text-left">
                    <span className="font-semibold">{row.case.case_key}</span>
                    <span className="mt-1 block text-xs font-normal text-[var(--studio-text-subtle)]">
                      #{row.case.ordinal}
                    </span>
                  </th>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2">
                      <EvaluationStatusBadge status={row.baseline_attempt.status} />
                      <span aria-hidden="true">→</span>
                      <EvaluationStatusBadge status={row.candidate_attempt.status} />
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    <div>Baseline {displayScore(row.baseline_attempt.score)}</div>
                    <div className="mt-1">Candidate {displayScore(row.candidate_attempt.score)}</div>
                    <div className="mt-1 font-semibold">Δ {displayScoreDelta(row.score_delta)}</div>
                  </td>
                  <td className="max-w-xl px-3 py-3 text-xs">
                    <div>
                      <span className="font-semibold">Baseline:</span>{' '}
                      <span className="whitespace-pre-wrap">{row.baseline_attempt.reason ?? '—'}</span>
                    </div>
                    <div className="mt-2">
                      <span className="font-semibold">Candidate:</span>{' '}
                      <span className="whitespace-pre-wrap">{row.candidate_attempt.reason ?? '—'}</span>
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    <div>Baseline {displayDuration(row.baseline_attempt.duration_ms)}</div>
                    <div className="mt-1">Candidate {displayDuration(row.candidate_attempt.duration_ms)}</div>
                    <div className="mt-1 font-semibold">Δ {displayDurationDelta(row.duration_delta_ms)}</div>
                  </td>
                  <td className="px-3 py-3 text-xs">
                    <div className="flex flex-col items-start gap-2">
                      {row.baseline_attempt.subject_execution === null ? (
                        <span className="text-[var(--studio-text-subtle)]">No baseline execution</span>
                      ) : (
                        <SemanticExecutionLink
                          execution={row.baseline_attempt.subject_execution}
                          label={`Open baseline evidence for ${row.case.case_key}`}
                        />
                      )}
                      {row.candidate_attempt.subject_execution === null ? (
                        <span className="text-[var(--studio-text-subtle)]">No candidate execution</span>
                      ) : (
                        <SemanticExecutionLink
                          execution={row.candidate_attempt.subject_execution}
                          label={`Open candidate evidence for ${row.case.case_key}`}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
