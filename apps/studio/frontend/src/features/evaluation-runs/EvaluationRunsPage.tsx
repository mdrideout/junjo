import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ActionButton } from '../../components/actions/action-button'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import {
  EvaluationRunComparisonQuerySchema,
  evaluationRunListQueryFromSearchParams,
  type EvaluationRunListQuery,
} from './schemas/query'
import { selectEvaluationRunListRequest } from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

const fieldClassName =
  'min-h-10 w-full rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 text-sm ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'

const EMPTY_LIST_REQUEST = {
  data: null,
  loading: false,
  error: null,
}

function evaluationRunsPath(query: EvaluationRunListQuery): string {
  const parameters = new URLSearchParams({ limit: String(query.limit) })
  if (query.dataset_id !== undefined) parameters.set('dataset_id', query.dataset_id)
  if (query.cursor !== undefined) parameters.set('cursor', query.cursor)
  return `/evaluation-runs?${parameters.toString()}`
}

function shortRevision(revision: string): string {
  return revision.length <= 12 ? revision : revision.slice(0, 12)
}

export default function EvaluationRunsPage() {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const query = useMemo(
    () => evaluationRunListQueryFromSearchParams(searchParameters),
    [searchParameters],
  )
  const request = useAppSelector((state) =>
    query === null
      ? EMPTY_LIST_REQUEST
      : selectEvaluationRunListRequest(state, query),
  )
  const [datasetId, setDatasetId] = useState(searchParameters.get('dataset_id') ?? '')
  const [baselineRunId, setBaselineRunId] = useState('')
  const [candidateRunId, setCandidateRunId] = useState('')
  const [comparisonError, setComparisonError] = useState<string | null>(null)

  useEffect(() => {
    setDatasetId(searchParameters.get('dataset_id') ?? '')
  }, [searchParameters])

  useEffect(() => {
    if (query !== null) dispatch(EvaluationRunsActions.fetchEvaluationRuns(query))
  }, [dispatch, query])

  const filterRuns = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const parameters = new URLSearchParams({ limit: '50' })
    if (datasetId.trim()) parameters.set('dataset_id', datasetId.trim())
    setSearchParameters(parameters)
  }

  const compareRuns = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const parsed = EvaluationRunComparisonQuerySchema.safeParse({
      baseline_run_id: baselineRunId.trim(),
      candidate_run_id: candidateRunId.trim(),
    })
    if (!parsed.success) {
      setComparisonError('Enter two different evaluation run IDs.')
      return
    }
    setComparisonError(null)
    const parameters = new URLSearchParams(parsed.data)
    navigate(`/evaluation-runs/compare?${parameters.toString()}`)
  }

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <header>
        <h1 className="m-0 text-3xl">Evaluation runs</h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--studio-text-muted)]">
          Inspect application-owned outcomes and follow exact semantic execution links to received Studio evidence.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-2">
        <form
          onSubmit={filterRuns}
          className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
        >
          <h2 className="m-0 text-lg">Filter runs</h2>
          <label className="mt-3 block text-sm font-medium">
            Dataset ID
            <input
              className={`${fieldClassName} mt-1 font-mono text-xs`}
              value={datasetId}
              onChange={(event) => setDatasetId(event.target.value)}
              placeholder="All datasets"
            />
          </label>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <ActionButton type="submit">Apply filter</ActionButton>
            {query?.dataset_id !== undefined && <AppLink to="/evaluation-runs">Clear filter</AppLink>}
          </div>
        </form>

        <form
          onSubmit={compareRuns}
          className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
        >
          <h2 className="m-0 text-lg">Compare two runs</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Baseline run ID
              <input
                className={`${fieldClassName} mt-1 font-mono text-xs`}
                value={baselineRunId}
                onChange={(event) => setBaselineRunId(event.target.value)}
                required
              />
            </label>
            <label className="text-sm font-medium">
              Candidate run ID
              <input
                className={`${fieldClassName} mt-1 font-mono text-xs`}
                value={candidateRunId}
                onChange={(event) => setCandidateRunId(event.target.value)}
                required
              />
            </label>
          </div>
          <div className="mt-3">
            <ActionButton type="submit">Compare runs</ActionButton>
          </div>
          {comparisonError !== null && (
            <p className="mt-2 text-sm text-[var(--studio-outcome-failed)]" role="alert">
              {comparisonError}
            </p>
          )}
        </form>
      </div>

      {query === null ? (
        <div
          className="rounded-xl border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-4 text-sm"
          role="alert"
        >
          The evaluation-run URL contains an invalid dataset, cursor, or page limit.
        </div>
      ) : request.loading && request.data === null ? (
        <p className="text-sm text-[var(--studio-text-muted)]">Loading evaluation runs…</p>
      ) : request.error !== null ? (
        <div
          className="rounded-xl border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-4 text-sm"
          role="alert"
        >
          {request.error}
        </div>
      ) : request.data === null || request.data.items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-6 text-sm text-[var(--studio-text-muted)]">
          No evaluation runs match this filter.
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
            <table className="w-full min-w-[70rem] text-left text-sm">
              <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
                <tr>
                  <th scope="col" className="px-3 py-3">Candidate</th>
                  <th scope="col" className="px-3 py-3">Dataset</th>
                  <th scope="col" className="px-3 py-3">Status</th>
                  <th scope="col" className="px-3 py-3">Attempts</th>
                  <th scope="col" className="px-3 py-3">Revision</th>
                  <th scope="col" className="px-3 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {request.data.items.map(({ run, dataset, attempt_counts: counts }) => (
                  <tr
                    key={run.id}
                    className="border-b border-[var(--studio-border)] last:border-0 hover:bg-[var(--studio-surface-hover)]"
                  >
                    <th scope="row" className="p-0 text-left">
                      <AppLink to={`/evaluation-runs/${encodeURIComponent(run.id)}`}>
                        <span className="block px-3 py-3 font-semibold no-underline">
                          {run.candidate_label}
                          <span className="mt-1 block font-mono text-xs font-normal text-[var(--studio-text-subtle)]">
                            {run.id}
                          </span>
                        </span>
                      </AppLink>
                    </th>
                    <td className="px-3 py-3">
                      <span className="font-medium">{dataset.name}</span>
                      <span className="mt-1 block font-mono text-xs text-[var(--studio-text-subtle)]">
                        {dataset.key}
                      </span>
                    </td>
                    <td className="px-3 py-3"><EvaluationStatusBadge status={run.status} /></td>
                    <td className="px-3 py-3 text-xs">
                      <span className="font-semibold">{counts.passed} passed</span>
                      <span className="mt-1 block text-[var(--studio-text-subtle)]">
                        {counts.failed} failed · {counts.error} error · {counts.queued} queued · {counts.total} total
                      </span>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs" title={run.source_revision}>
                      {shortRevision(run.source_revision)}
                    </td>
                    <td className="px-3 py-3 text-xs text-[var(--studio-text-muted)]">
                      {new Date(run.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <nav aria-label="Evaluation run pages" className="flex flex-wrap items-center justify-between gap-3">
            <div>
              {query.cursor !== undefined && (
                <AppLink to={evaluationRunsPath({ dataset_id: query.dataset_id, limit: query.limit })}>
                  First page
                </AppLink>
              )}
            </div>
            {request.data.next_cursor !== null && (
              <AppLink
                to={evaluationRunsPath({
                  dataset_id: query.dataset_id,
                  cursor: request.data.next_cursor,
                  limit: query.limit,
                })}
              >
                Next page
              </AppLink>
            )}
          </nav>
        </>
      )}
    </div>
  )
}
