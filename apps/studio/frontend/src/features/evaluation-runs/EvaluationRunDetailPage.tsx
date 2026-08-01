import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import { SemanticExecutionLink } from './components/SemanticExecutionLink'
import { EvaluationIdSchema } from './schemas/evaluation-runs'
import { selectEvaluationRunDetailRequest } from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

const filterClassName =
  'min-h-9 rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-2 py-1 text-sm'

function displayPassRate(passed: number, judged: number): string {
  return judged === 0 ? 'Not judged' : `${Math.round((passed / judged) * 100)}%`
}

function displayJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

export default function EvaluationRunDetailPage() {
  const { runId } = useParams()
  const parsedRunId = EvaluationIdSchema.safeParse(runId)
  const validatedRunId = parsedRunId.success ? parsedRunId.data : ''
  const dispatch = useAppDispatch()
  const request = useAppSelector((state) =>
    selectEvaluationRunDetailRequest(state, validatedRunId),
  )
  const [targetFilter, setTargetFilter] = useState('')
  const [evaluationFilter, setEvaluationFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    if (validatedRunId) dispatch(EvaluationRunsActions.fetchEvaluationRun(validatedRunId))
  }, [dispatch, validatedRunId])

  if (!parsedRunId.success) {
    return <ErrorPage title="Invalid evaluation run" message="A non-empty evaluation run ID is required." />
  }
  if (request.loading && request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">Loading evaluation run…</div>
  }
  if (request.error !== null) {
    return <ErrorPage title="Evaluation run unavailable" message={request.error} />
  }
  if (request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">No evaluation run found.</div>
  }

  const { run, dataset, cases } = request.data
  const targetOptions = [...new Map(cases.map((item) => {
    const identity = JSON.stringify([
      item.case.target_kind,
      item.case.target_key,
      item.case.input_version,
    ])
    return [identity, item.case] as const
  })).entries()]
  const evaluationOptions = [...new Set(
    cases.map((item) => item.case.evaluation_name),
  )].sort()
  const outcomePriority = { error: 0, failed: 1, queued: 2, passed: 3 }
  const visibleCases = cases
    .filter((item) => {
      const targetIdentity = JSON.stringify([
        item.case.target_kind,
        item.case.target_key,
        item.case.input_version,
      ])
      return (
        (!targetFilter || targetFilter === targetIdentity)
        && (!evaluationFilter || evaluationFilter === item.case.evaluation_name)
        && (!statusFilter || statusFilter === item.attempt.status)
      )
    })
    .sort(
      (left, right) =>
        outcomePriority[left.attempt.status] - outcomePriority[right.attempt.status]
        || left.case.ordinal - right.case.ordinal,
    )
  const passed = visibleCases.filter((item) => item.attempt.status === 'passed').length
  const failed = visibleCases.filter((item) => item.attempt.status === 'failed').length
  const errors = visibleCases.filter((item) => item.attempt.status === 'error').length
  const judged = passed + failed

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to="/evaluation-runs">Evaluations</AppLink>
        <span aria-hidden="true">/</span>
        <AppLink to={`/evaluation-runs/datasets/${encodeURIComponent(dataset.id)}`}>
          {dataset.name}
        </AppLink>
        <span aria-hidden="true">/</span>
        <span>{run.run_label}</span>
      </nav>

      <header className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-[var(--studio-text-muted)]">
              {dataset.name}
            </div>
            <h1 className="m-0 mt-1">{run.run_label}</h1>
          </div>
          <EvaluationStatusBadge status={run.status} />
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Dataset</dt>
            <dd className="mt-1 text-sm font-semibold">
              <AppLink to={`/evaluation-runs/datasets/${encodeURIComponent(dataset.id)}`}>
                {dataset.name}
              </AppLink>
            </dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Git Commit</dt>
            <dd className="mt-1 break-all font-mono text-xs">{run.source_revision}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Created</dt>
            <dd className="mt-1 text-sm">{new Date(run.created_at).toLocaleString()}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Completed</dt>
            <dd className="mt-1 text-sm">
              {run.completed_at === null
                ? 'Still active'
                : new Date(run.completed_at).toLocaleString()}
            </dd>
          </div>
        </dl>
      </header>

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="m-0">Evaluation results</h2>
            <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
              Binary results for each Node, Workflow, or Agent test in the dataset.
            </p>
          </div>
          <dl className="flex flex-wrap gap-2 text-xs">
            <div className="rounded-lg bg-[var(--studio-surface)] px-3 py-2">
              <dt className="text-[var(--studio-text-subtle)]">Pass rate</dt>
              <dd className="mt-1 font-semibold">{displayPassRate(passed, judged)}</dd>
            </div>
            <div className="rounded-lg bg-[var(--studio-surface)] px-3 py-2">
              <dt className="text-[var(--studio-text-subtle)]">Passed / failed</dt>
              <dd className="mt-1 font-semibold">{passed} / {failed}</dd>
            </div>
            <div className="rounded-lg bg-[var(--studio-surface)] px-3 py-2">
              <dt className="text-[var(--studio-text-subtle)]">Errors</dt>
              <dd className="mt-1 font-semibold">{errors}</dd>
            </div>
          </dl>
        </div>

        <div className="mb-3 flex flex-wrap gap-2" aria-label="Evaluation result filters">
          <select
            className={filterClassName}
            aria-label="Target scope"
            value={targetFilter}
            onChange={(event) => setTargetFilter(event.target.value)}
          >
            <option value="">All targets</option>
            {targetOptions.map(([identity, item]) => (
              <option key={identity} value={identity}>
                {item.target_kind} · {item.target_key} · input v{item.input_version}
              </option>
            ))}
          </select>
          <select
            className={filterClassName}
            aria-label="Evaluation"
            value={evaluationFilter}
            onChange={(event) => setEvaluationFilter(event.target.value)}
          >
            <option value="">All evaluations</option>
            {evaluationOptions.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          <select
            className={filterClassName}
            aria-label="Result"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All results</option>
            <option value="passed">Passed</option>
            <option value="failed">Failed</option>
            <option value="error">Error</option>
            <option value="queued">Queued</option>
          </select>
        </div>

        {visibleCases.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-5 text-sm text-[var(--studio-text-muted)]">
            No evaluation results match these filters.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
            <table className="w-full min-w-[68rem] text-left text-sm">
              <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
                <tr>
                  <th scope="col" className="px-3 py-3">Scope</th>
                  <th scope="col" className="px-3 py-3">Evaluation</th>
                  <th scope="col" className="px-3 py-3">Result</th>
                  <th scope="col" className="px-3 py-3">Reason</th>
                  <th scope="col" className="px-3 py-3">Spans</th>
                </tr>
              </thead>
              <tbody>
                {visibleCases.map((item) => (
                  <tr key={item.case.id} className="border-b border-[var(--studio-border)] last:border-0 align-top">
                    <th scope="row" className="px-3 py-3 text-left">
                      <span className="font-semibold capitalize">{item.case.target_kind}</span>
                      <span className="mt-1 block font-mono text-xs font-normal">
                        {item.case.target_key}
                      </span>
                      <span className="mt-1 block text-xs font-normal text-[var(--studio-text-subtle)]">
                        Input v{item.case.input_version}
                      </span>
                    </th>
                    <td className="max-w-md px-3 py-3">
                      <span className="font-semibold">{item.case.evaluation_name}</span>
                      <details className="mt-2 text-xs text-[var(--studio-text-muted)]">
                        <summary className="cursor-pointer">Test details</summary>
                        <dl className="mt-2 space-y-2">
                          <div>
                            <dt className="font-semibold">Input</dt>
                            <dd><pre className="mt-1 overflow-auto whitespace-pre-wrap">{displayJson(item.case.input_json)}</pre></dd>
                          </div>
                          <div>
                            <dt className="font-semibold">Pass condition</dt>
                            <dd><pre className="mt-1 overflow-auto whitespace-pre-wrap">{displayJson(item.case.expectation_json)}</pre></dd>
                          </div>
                          <div>
                            <dt className="font-semibold">Origin</dt>
                            <dd>{item.case.origin}</dd>
                          </div>
                          <div>
                            <dt className="font-semibold">Internal case key</dt>
                            <dd className="font-mono">{item.case.case_key}</dd>
                          </div>
                          <div>
                            <dt className="font-semibold">Evaluator implementation</dt>
                            <dd className="font-mono">{item.case.evaluator_key} v{item.case.evaluator_version}</dd>
                          </div>
                          {item.case.source_execution !== null && (
                            <div>
                              <dt className="font-semibold">Generated from</dt>
                              <dd>
                                <SemanticExecutionLink
                                  execution={item.case.source_execution}
                                  label="View source spans"
                                />
                              </dd>
                            </div>
                          )}
                        </dl>
                      </details>
                    </td>
                    <td className="px-3 py-3">
                      <EvaluationStatusBadge status={item.attempt.status} />
                    </td>
                    <td className="max-w-xl whitespace-pre-wrap px-3 py-3 text-xs">
                      {item.attempt.reason ?? '—'}
                    </td>
                    <td className="px-3 py-3 text-xs">
                      {item.attempt.subject_execution === null ? (
                        <span className="text-[var(--studio-text-subtle)]">Pending</span>
                      ) : (
                        <SemanticExecutionLink
                          execution={item.attempt.subject_execution}
                          label="View spans"
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
