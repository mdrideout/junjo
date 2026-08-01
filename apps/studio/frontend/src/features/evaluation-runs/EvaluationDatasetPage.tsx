import { useEffect, useMemo } from 'react'
import { useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import { SemanticExecutionLink } from './components/SemanticExecutionLink'
import { EvaluationIdSchema } from './schemas/evaluation-runs'
import {
  selectEvaluationDatasetDetailRequest,
  selectEvaluationRunListRequest,
} from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

function displayJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function displayCaseValue(value: unknown, preferredKey: string): string {
  const preferredValue =
    typeof value === 'object' && value !== null
      ? (value as Record<string, unknown>)[preferredKey]
      : undefined
  return typeof preferredValue === 'string' ? preferredValue : displayJson(value)
}

function displayRate(rate: number | null): string {
  return rate === null ? 'Not judged' : `${Math.round(rate * 100)}%`
}

export default function EvaluationDatasetPage() {
  const { datasetId } = useParams()
  const parsedDatasetId = EvaluationIdSchema.safeParse(datasetId)
  const validatedDatasetId = parsedDatasetId.success ? parsedDatasetId.data : ''
  const dispatch = useAppDispatch()
  const runQuery = useMemo(
    () => ({ dataset_id: validatedDatasetId, limit: 50 }),
    [validatedDatasetId],
  )
  const datasetRequest = useAppSelector((state) =>
    selectEvaluationDatasetDetailRequest(state, validatedDatasetId),
  )
  const runsRequest = useAppSelector((state) =>
    selectEvaluationRunListRequest(state, runQuery),
  )

  useEffect(() => {
    if (!validatedDatasetId) return
    dispatch(EvaluationRunsActions.fetchEvaluationDataset(validatedDatasetId))
    dispatch(EvaluationRunsActions.fetchEvaluationRuns(runQuery))
  }, [dispatch, runQuery, validatedDatasetId])

  if (!parsedDatasetId.success) {
    return <ErrorPage title="Invalid evaluation dataset" message="A non-empty dataset ID is required." />
  }
  if (datasetRequest.loading && datasetRequest.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">Loading evaluation dataset…</div>
  }
  if (datasetRequest.error !== null) {
    return <ErrorPage title="Evaluation dataset unavailable" message={datasetRequest.error} />
  }
  if (datasetRequest.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">No evaluation dataset found.</div>
  }

  const { dataset, cases } = datasetRequest.data
  const runs = runsRequest.data?.items ?? []

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to="/evaluation-runs">Evaluations</AppLink>
        <span aria-hidden="true">/</span>
        <span>{dataset.name}</span>
      </nav>

      <header className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-[var(--studio-text-muted)]">
              {dataset.application_key}
            </div>
            <h1 className="m-0 mt-1">{dataset.name}</h1>
            {dataset.description !== null && (
              <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
                {dataset.description}
              </p>
            )}
          </div>
          <span className="inline-flex rounded-full bg-[var(--studio-page)] px-2.5 py-1 text-xs font-semibold capitalize">
            {dataset.status}
          </span>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Tests</dt>
            <dd className="mt-1 text-lg font-semibold">{cases.length}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Created</dt>
            <dd className="mt-1 text-sm">{new Date(dataset.created_at).toLocaleString()}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Locked</dt>
            <dd className="mt-1 text-sm">
              {dataset.locked_at === null
                ? 'Not locked'
                : new Date(dataset.locked_at).toLocaleString()}
            </dd>
          </div>
        </dl>
      </header>

      <section>
        <h2 className="m-0">Tests</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Inputs, pass conditions, and execution scope locked into this dataset.
        </p>
        {cases.length === 0 ? (
          <div className="mt-3 rounded-xl border border-dashed border-[var(--studio-border-strong)] p-5 text-sm text-[var(--studio-text-muted)]">
            This draft dataset has no tests.
          </div>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
            <table className="w-full min-w-[76rem] text-left text-sm">
              <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
                <tr>
                  <th scope="col" className="px-3 py-3">Scope</th>
                  <th scope="col" className="px-3 py-3">Evaluation</th>
                  <th scope="col" className="px-3 py-3">Input</th>
                  <th scope="col" className="px-3 py-3">Pass condition</th>
                  <th scope="col" className="px-3 py-3">Origin</th>
                </tr>
              </thead>
              <tbody>
                {[...cases].sort((left, right) => left.ordinal - right.ordinal).map((item) => (
                  <tr key={item.id} className="border-b border-[var(--studio-border)] last:border-0 align-top">
                    <th scope="row" className="px-3 py-3 text-left">
                      <span className="font-semibold capitalize">{item.target_kind}</span>
                      <span className="mt-1 block font-mono text-xs font-normal">
                        {item.target_key}
                      </span>
                      <span className="mt-1 block text-xs font-normal text-[var(--studio-text-subtle)]">
                        Input v{item.input_version}
                      </span>
                    </th>
                    <td className="px-3 py-3">
                      <span className="font-semibold">{item.evaluation_name}</span>
                      <details className="mt-2 text-xs text-[var(--studio-text-muted)]">
                        <summary className="cursor-pointer">Implementation details</summary>
                        <div className="mt-2 font-mono">
                          {item.evaluator_key} v{item.evaluator_version}
                        </div>
                        <div className="mt-1 font-mono">Case key: {item.case_key}</div>
                      </details>
                    </td>
                    <td className="max-w-sm px-3 py-3">
                      <p className="m-0 whitespace-pre-wrap text-sm">
                        {displayCaseValue(item.input_json, 'message')}
                      </p>
                    </td>
                    <td className="max-w-sm px-3 py-3">
                      <p className="m-0 whitespace-pre-wrap text-sm">
                        {displayCaseValue(item.expectation_json, 'rubric')}
                      </p>
                    </td>
                    <td className="px-3 py-3 text-xs">
                      <span className="capitalize">{item.origin}</span>
                      {item.source_execution !== null && (
                        <div className="mt-2">
                          <SemanticExecutionLink
                            execution={item.source_execution}
                            label="View source spans"
                          />
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="m-0">Run history</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Every execution of this same locked test set.
        </p>
        {runsRequest.loading && runsRequest.data === null ? (
          <p className="mt-3 text-sm text-[var(--studio-text-muted)]">Loading run history…</p>
        ) : runsRequest.error !== null ? (
          <p className="mt-3 text-sm text-[var(--studio-outcome-failed)]" role="alert">
            {runsRequest.error}
          </p>
        ) : runs.length === 0 ? (
          <div className="mt-3 rounded-xl border border-dashed border-[var(--studio-border-strong)] p-5 text-sm text-[var(--studio-text-muted)]">
            This dataset has not been run yet.
          </div>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
            <table className="w-full min-w-[52rem] text-left text-sm">
              <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
                <tr>
                  <th scope="col" className="px-3 py-3">Run</th>
                  <th scope="col" className="px-3 py-3">Results</th>
                  <th scope="col" className="px-3 py-3">Status</th>
                  <th scope="col" className="px-3 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((item) => (
                  <tr key={item.run.id} className="border-b border-[var(--studio-border)] last:border-0">
                    <th scope="row" className="p-0 text-left">
                      <AppLink to={`/evaluation-runs/${encodeURIComponent(item.run.id)}`}>
                        <span className="block px-3 py-3 font-semibold">{item.run.run_label}</span>
                      </AppLink>
                    </th>
                    <td className="px-3 py-3">
                      <span className="font-semibold">{displayRate(item.outcome_summary.pass_rate)} pass</span>
                      <span className="mt-1 block text-xs text-[var(--studio-text-subtle)]">
                        {item.outcome_summary.passed} passed · {item.outcome_summary.failed} failed · {item.outcome_summary.error} error
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <EvaluationStatusBadge status={item.run.status} />
                    </td>
                    <td className="px-3 py-3 text-xs text-[var(--studio-text-muted)]">
                      {new Date(item.run.created_at).toLocaleString()}
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
