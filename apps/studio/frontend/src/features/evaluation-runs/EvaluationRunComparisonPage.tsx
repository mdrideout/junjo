import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import { ExecutionEvidenceLink } from './components/ExecutionEvidenceLink'
import type { EvaluationCase } from './schemas/evaluation-runs'
import { evaluationRunComparisonQueryFromSearchParams } from './schemas/query'
import {
  selectEvaluationRunComparison,
  selectEvaluationRunDetailRequest,
  type EvaluationTransition,
} from './store/selectors'
import { EvaluationRunsActions } from './store/slice'
import { evaluationTargetLabel } from './target-label'

const EMPTY_COMPARISON_QUERY = {
  baseline_run_id: '',
  candidate_run_id: '',
}

const filterClassName =
  'min-h-9 rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-2 py-1 text-sm'

function displayRate(rate: number | null): string {
  return rate === null ? 'Not judged' : `${Math.round(rate * 100)}%`
}

function displayTransition(transition: EvaluationTransition): string {
  return transition.replace('_', ' ')
}

function targetIdentity(item: EvaluationCase): string {
  return JSON.stringify([item.target_kind, item.target_key, item.input_version])
}

export default function EvaluationRunComparisonPage() {
  const [searchParameters, setSearchParameters] = useSearchParams()
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
  const [transitionFilter, setTransitionFilter] = useState<EvaluationTransition | ''>('')
  const [outcomeFilter, setOutcomeFilter] =
    useState<'passed' | 'failed' | 'error' | 'queued' | ''>('')

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

  const {
    baseline_run: baseline,
    candidate_run: candidate,
    baseline_summary: baselineSummary,
    candidate_summary: candidateSummary,
    transition_counts: transitionCounts,
    dataset,
    rows,
  } = comparison.data
  const targetOptions = new Map<string, EvaluationCase>()
  const evaluationOptions = new Set<string>()
  for (const item of baselineRequest.data?.cases ?? []) {
    targetOptions.set(targetIdentity(item.case), item.case)
    evaluationOptions.add(item.case.evaluation_name)
  }
  const selectedTarget = query.target_kind === undefined
    ? ''
    : JSON.stringify([query.target_kind, query.target_key, query.input_version])
  const selectedEvaluation = query.evaluation_name ?? ''
  const visibleRows = rows.filter(
    (row) =>
      (!transitionFilter || row.transition === transitionFilter)
      && (!outcomeFilter || row.candidate_attempt.status === outcomeFilter),
  )

  const updateScope = (
    fields: readonly string[],
    values: Record<string, string | number> = {},
  ) => {
    const next = new URLSearchParams(searchParameters)
    for (const field of fields) next.delete(field)
    for (const [field, value] of Object.entries(values)) next.set(field, String(value))
    setSearchParameters(next)
  }

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to="/evaluation-runs">Evaluations</AppLink>
        <span aria-hidden="true">/</span>
        <AppLink to={`/evaluation-runs/datasets/${encodeURIComponent(dataset.id)}`}>
          {dataset.name}
        </AppLink>
        <span aria-hidden="true">/</span>
        <span>Comparison</span>
      </nav>

      <header>
        <h1 className="m-0">Compare runs</h1>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          See which tests improved or regressed across the same locked dataset.
        </p>
      </header>

      <section className="grid gap-4 lg:grid-cols-2" aria-label="Compared runs">
        {[
          { role: 'Baseline', run: baseline, summary: baselineSummary },
          { role: 'Candidate', run: candidate, summary: candidateSummary },
        ].map(({ role, run, summary }) => (
          <article
            key={run.id}
            className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--studio-text-subtle)]">
                  {role}
                </div>
                <h2 className="m-0 mt-1">{run.run_label}</h2>
              </div>
              <EvaluationStatusBadge status={run.status} />
            </div>
            <p className="mt-3 text-sm font-semibold">
              {displayRate(summary.pass_rate)} pass · {summary.passed} passed · {summary.failed} failed
            </p>
            <div className="mt-3">
              <AppLink to={`/evaluation-runs/${encodeURIComponent(run.id)}`}>View run</AppLink>
            </div>
          </article>
        ))}
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="m-0">Test changes</h2>
            <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
              Binary outcomes aligned by the same immutable dataset tests.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="text-xs font-medium">
              Target
              <select
                className={`${filterClassName} ml-2`}
                value={selectedTarget}
                onChange={(event) => {
                  const fields = ['target_kind', 'target_key', 'input_version'] as const
                  if (!event.target.value) {
                    updateScope(fields)
                    return
                  }
                  const [targetKind, targetKey, inputVersion] = JSON.parse(
                    event.target.value,
                  ) as ['node' | 'workflow' | 'agent', string, number]
                  updateScope(fields, {
                    target_kind: targetKind,
                    target_key: targetKey,
                    input_version: inputVersion,
                  })
                }}
              >
                <option value="">All targets</option>
                {[...targetOptions.entries()].map(([identity, item]) => (
                  <option key={identity} value={identity}>
                    {evaluationTargetLabel(item.target_kind, item.target_name)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium">
              Evaluation
              <select
                className={`${filterClassName} ml-2`}
                value={selectedEvaluation}
                onChange={(event) => {
                  updateScope(
                    ['evaluation_name'],
                    event.target.value
                      ? { evaluation_name: event.target.value }
                      : {},
                  )
                }}
              >
                <option value="">All evaluations</option>
                {[...evaluationOptions].sort().map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium">
              Change
              <select
                className={`${filterClassName} ml-2`}
                value={transitionFilter}
                onChange={(event) => setTransitionFilter(event.target.value as EvaluationTransition | '')}
              >
                <option value="">All ({rows.length})</option>
                {(Object.keys(transitionCounts) as EvaluationTransition[]).map((transition) => (
                  <option key={transition} value={transition}>
                    {displayTransition(transition)} ({transitionCounts[transition]})
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium">
              Candidate result
              <select
                className={`${filterClassName} ml-2`}
                value={outcomeFilter}
                onChange={(event) => setOutcomeFilter(
                  event.target.value as typeof outcomeFilter,
                )}
              >
                <option value="">All results</option>
                <option value="passed">Passed</option>
                <option value="failed">Failed</option>
                <option value="error">Error</option>
                <option value="queued">Queued</option>
              </select>
            </label>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
          <table className="w-full min-w-[76rem] text-left text-sm">
            <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
              <tr>
                <th scope="col" className="px-3 py-3">Target</th>
                <th scope="col" className="px-3 py-3">Evaluation</th>
                <th scope="col" className="px-3 py-3">Change</th>
                <th scope="col" className="px-3 py-3">Result</th>
                <th scope="col" className="px-3 py-3">Reason</th>
                <th scope="col" className="px-3 py-3">Spans</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.case.id} className="border-b border-[var(--studio-border)] last:border-0 align-top">
                  <th scope="row" className="px-3 py-3 text-left">
                    <span className="font-semibold">
                      {evaluationTargetLabel(row.case.target_kind, row.case.target_name)}
                    </span>
                  </th>
                  <td className="px-3 py-3 font-semibold">{row.case.evaluation_name}</td>
                  <td className="px-3 py-3 font-semibold capitalize">
                    {displayTransition(row.transition)}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2">
                      <EvaluationStatusBadge status={row.baseline_attempt.status} />
                      <span aria-hidden="true">→</span>
                      <EvaluationStatusBadge status={row.candidate_attempt.status} />
                    </div>
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
                  <td className="px-3 py-3 text-xs">
                    <div className="flex flex-col items-start gap-2">
                      {row.baseline_attempt.subject_evidence === null ? (
                        <span className="text-[var(--studio-text-subtle)]">Baseline pending</span>
                      ) : (
                        <ExecutionEvidenceLink
                          evidence={row.baseline_attempt.subject_evidence}
                          label="View baseline spans"
                        />
                      )}
                      {row.candidate_attempt.subject_evidence === null ? (
                        <span className="text-[var(--studio-text-subtle)]">Candidate pending</span>
                      ) : (
                        <ExecutionEvidenceLink
                          evidence={row.candidate_attempt.subject_evidence}
                          label="View candidate spans"
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
