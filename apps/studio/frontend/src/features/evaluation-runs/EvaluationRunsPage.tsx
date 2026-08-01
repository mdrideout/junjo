import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ActionButton } from '../../components/actions/action-button'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import type {
  EvaluationNameFacet,
  EvaluationRunListItem,
  EvaluationTargetFacet,
} from './schemas/evaluation-runs'
import {
  EvaluationRunListQuerySchema,
  evaluationRunListQueryFromSearchParams,
  type EvaluationRunListQuery,
} from './schemas/query'
import {
  selectEvaluationDatasetListRequest,
  selectEvaluationRunListRequest,
} from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

const fieldClassName =
  'min-h-10 w-full rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 text-sm ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--studio-focus-ring)]'

const EMPTY_LIST_REQUEST = {
  data: null,
  loading: false,
  error: null,
}
const EMPTY_RUN_ITEMS: EvaluationRunListItem[] = []

type QueryPatch = Partial<
  Omit<
    EvaluationRunListQuery,
    | 'target_kind'
    | 'target_key'
    | 'input_version'
    | 'evaluation_name'
  >
> & {
  target_kind?: EvaluationRunListQuery['target_kind'] | null
  target_key?: string | null
  input_version?: number | null
  evaluation_name?: string | null
}

function evaluationRunsPath(query: EvaluationRunListQuery): string {
  const parameters = new URLSearchParams({ limit: String(query.limit) })
  const stringFields = [
    'dataset_id',
    'target_kind',
    'target_key',
    'evaluation_name',
    'cursor',
  ] as const
  for (const field of stringFields) {
    const value = query[field]
    if (value !== undefined) parameters.set(field, value)
  }
  if (query.input_version !== undefined) {
    parameters.set('input_version', String(query.input_version))
  }
  return `/evaluation-runs?${parameters.toString()}`
}

function displayRate(rate: number | null): string {
  return rate === null ? 'Not judged' : `${Math.round(rate * 100)}%`
}

function targetIdentity(facet: EvaluationTargetFacet): string {
  return JSON.stringify([facet.target_kind, facet.target_key, facet.input_version])
}

export default function EvaluationRunsPage() {
  const [searchParameters, setSearchParameters] = useSearchParams()
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const query = useMemo(
    () => evaluationRunListQueryFromSearchParams(searchParameters),
    [searchParameters],
  )
  const datasetsRequest = useAppSelector(selectEvaluationDatasetListRequest)
  const request = useAppSelector((state) =>
    query === null || query.dataset_id === undefined
      ? EMPTY_LIST_REQUEST
      : selectEvaluationRunListRequest(state, query),
  )
  const [baselineRunId, setBaselineRunId] = useState('')
  const [candidateRunId, setCandidateRunId] = useState('')

  useEffect(() => {
    dispatch(EvaluationRunsActions.fetchEvaluationDatasets())
  }, [dispatch])

  useEffect(() => {
    if (query?.dataset_id !== undefined) {
      dispatch(EvaluationRunsActions.fetchEvaluationRuns(query))
    }
  }, [dispatch, query])

  const selectedDataset = datasetsRequest.data?.items.find(
    (dataset) => dataset.id === query?.dataset_id,
  )
  const listItems = request.data?.items ?? EMPTY_RUN_ITEMS
  const targetFacets = useMemo(() => {
    const facets = new Map<string, EvaluationTargetFacet>()
    for (const item of listItems) {
      for (const facet of item.target_facets) facets.set(targetIdentity(facet), facet)
    }
    return [...facets.values()].sort((left, right) =>
      targetIdentity(left).localeCompare(targetIdentity(right)))
  }, [listItems])
  const evaluationFacets = useMemo(() => {
    const facets = new Map<string, EvaluationNameFacet>()
    for (const item of listItems) {
      for (const facet of item.evaluation_facets) {
        facets.set(facet.evaluation_name, facet)
      }
    }
    return [...facets.values()].sort((left, right) =>
      left.evaluation_name.localeCompare(right.evaluation_name))
  }, [listItems])

  const selectedTarget = query?.target_kind === undefined
    ? ''
    : JSON.stringify([query.target_kind, query.target_key, query.input_version])
  const selectedEvaluation = query?.evaluation_name ?? ''

  const updateQuery = (patch: QueryPatch) => {
    if (query === null) return
    const next = { ...query, ...patch, cursor: undefined }
    for (const [key, value] of Object.entries(next)) {
      if (value === null || value === undefined) delete next[key as keyof typeof next]
    }
    const validated = EvaluationRunListQuerySchema.parse(next)
    setSearchParameters(
      new URL(evaluationRunsPath(validated), window.location.origin).searchParams,
    )
  }

  const completedRuns = listItems.filter((item) => item.run.status === 'completed')
  const selectedCandidateId = listItems.some((item) => item.run.id === candidateRunId)
    ? candidateRunId
    : completedRuns[0]?.run.id ?? ''
  const selectedBaselineId = listItems.some(
    (item) => item.run.id === baselineRunId && item.run.id !== selectedCandidateId,
  )
    ? baselineRunId
    : completedRuns.find((item) => item.run.id !== selectedCandidateId)?.run.id ?? ''

  const compareRuns = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (query === null || !selectedBaselineId || !selectedCandidateId) return
    const parameters = new URLSearchParams({
      baseline_run_id: selectedBaselineId,
      candidate_run_id: selectedCandidateId,
    })
    const scopeFields = [
      'target_kind',
      'target_key',
      'input_version',
      'evaluation_name',
    ] as const
    for (const field of scopeFields) {
      const value = query[field]
      if (value !== undefined) parameters.set(field, String(value))
    }
    navigate(`/evaluation-runs/compare?${parameters.toString()}`)
  }

  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <header>
        <h1 className="m-0">Evaluations</h1>
        <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
          Select a dataset, follow outcomes across code revisions, and open the exact
          Node, Workflow, or Agent execution behind every result.
        </p>
      </header>

      <section className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4">
        <div className="grid gap-4 lg:grid-cols-3">
          <label className="text-sm font-medium">
            Dataset
            <select
              className={`${fieldClassName} mt-1`}
              value={query?.dataset_id ?? ''}
              onChange={(event) => {
                setBaselineRunId('')
                setCandidateRunId('')
                setSearchParameters(
                  event.target.value
                    ? { dataset_id: event.target.value, limit: '50' }
                    : {},
                )
              }}
            >
              <option value="">Choose a dataset</option>
              {datasetsRequest.data?.items.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.name} · {dataset.application_key}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium">
            Target scope
            <select
              className={`${fieldClassName} mt-1`}
              value={selectedTarget}
              disabled={query?.dataset_id === undefined}
              onChange={(event) => {
                if (!event.target.value) {
                  updateQuery({
                    target_kind: null,
                    target_key: null,
                    input_version: null,
                  })
                  return
                }
                const [targetKind, targetKey, inputVersion] = JSON.parse(
                  event.target.value,
                ) as ['node' | 'workflow' | 'agent', string, number]
                updateQuery({
                  target_kind: targetKind,
                  target_key: targetKey,
                  input_version: inputVersion,
                })
              }}
            >
              <option value="">All targets</option>
              {targetFacets.map((facet) => (
                <option key={targetIdentity(facet)} value={targetIdentity(facet)}>
                  {facet.target_kind} · {facet.target_key} · input v{facet.input_version}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium">
            Evaluation
            <select
              className={`${fieldClassName} mt-1`}
              value={selectedEvaluation}
              disabled={query?.dataset_id === undefined}
              onChange={(event) => {
                updateQuery({ evaluation_name: event.target.value || null })
              }}
            >
              <option value="">All evaluations</option>
              {evaluationFacets.map((facet) => (
                <option key={facet.evaluation_name} value={facet.evaluation_name}>
                  {facet.evaluation_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {datasetsRequest.loading && datasetsRequest.data === null && (
          <p className="mt-3 text-sm text-[var(--studio-text-muted)]">Loading datasets…</p>
        )}
        {datasetsRequest.error !== null && (
          <p className="mt-3 text-sm text-[var(--studio-outcome-failed)]" role="alert">
            {datasetsRequest.error}
          </p>
        )}
        {datasetsRequest.data?.next_cursor !== null
          && datasetsRequest.data?.next_cursor !== undefined && (
          <p className="mt-3 text-xs text-[var(--studio-text-subtle)]">
            Showing the 100 most recent datasets.
          </p>
        )}
      </section>

      {query === null ? (
        <div
          className="rounded-xl border border-[var(--studio-outcome-failed)] bg-[var(--studio-outcome-failed-bg)] p-4 text-sm"
          role="alert"
        >
          The evaluation URL contains an invalid filter, cursor, or page limit.
        </div>
      ) : query.dataset_id === undefined ? (
        <div className="rounded-xl border border-dashed border-[var(--studio-border-strong)] p-6 text-sm text-[var(--studio-text-muted)]">
          Choose a dataset to inspect its evaluation history.
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
          No evaluation runs match this scope.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="m-0">
                {selectedDataset === undefined ? (
                  'Dataset history'
                ) : (
                  <AppLink
                    to={`/evaluation-runs/datasets/${encodeURIComponent(selectedDataset.id)}`}
                  >
                    {selectedDataset.name}
                  </AppLink>
                )}
              </h2>
              <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
                {selectedDataset?.description ?? 'Runs for this locked dataset.'}
              </p>
            </div>
            <form onSubmit={compareRuns} className="flex flex-wrap items-end gap-2">
              <label className="text-xs font-medium">
                Baseline
                <select
                  className={`${fieldClassName} mt-1 min-w-44`}
                  value={selectedBaselineId}
                  onChange={(event) => setBaselineRunId(event.target.value)}
                >
                  <option value="">Select run</option>
                  {completedRuns
                    .filter((item) => item.run.id !== selectedCandidateId)
                    .map((item) => (
                      <option key={item.run.id} value={item.run.id}>
                        {item.run.run_label}
                      </option>
                    ))}
                </select>
              </label>
              <label className="text-xs font-medium">
                Candidate
                <select
                  className={`${fieldClassName} mt-1 min-w-44`}
                  value={selectedCandidateId}
                  onChange={(event) => setCandidateRunId(event.target.value)}
                >
                  <option value="">Select run</option>
                  {completedRuns.map((item) => (
                    <option key={item.run.id} value={item.run.id}>
                      {item.run.run_label}
                    </option>
                  ))}
                </select>
              </label>
              <ActionButton
                type="submit"
                disabled={!selectedBaselineId || !selectedCandidateId}
              >
                Compare
              </ActionButton>
            </form>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
            <table className="w-full min-w-[66rem] text-left text-sm">
              <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
                <tr>
                  <th scope="col" className="px-3 py-3">Run</th>
                  <th scope="col" className="px-3 py-3">Scope</th>
                  <th scope="col" className="px-3 py-3">Results</th>
                  <th scope="col" className="px-3 py-3">Status</th>
                  <th scope="col" className="px-3 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {request.data.items.map((item) => {
                  const { run, outcome_summary: outcome } = item
                  return (
                    <tr
                      key={run.id}
                      className="border-b border-[var(--studio-border)] last:border-0 hover:bg-[var(--studio-surface-hover)]"
                    >
                      <th scope="row" className="p-0 text-left">
                        <AppLink to={`/evaluation-runs/${encodeURIComponent(run.id)}`}>
                          <span className="block px-3 py-3 font-semibold no-underline">
                            {run.run_label}
                          </span>
                        </AppLink>
                      </th>
                      <td className="px-3 py-3 text-xs">
                        <div>
                          {item.target_facets.map((facet) => (
                            <span
                              key={targetIdentity(facet)}
                              className="mr-1 mt-1 inline-block rounded-full bg-[var(--studio-page)] px-2 py-1"
                            >
                              {facet.target_kind} · {facet.target_key} · input v{facet.input_version}
                            </span>
                          ))}
                        </div>
                        <div className="mt-2 text-[var(--studio-text-muted)]">
                          {item.evaluation_facets.map((facet) => facet.evaluation_name).join(' · ')}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <span className="font-semibold">{displayRate(outcome.pass_rate)} pass</span>
                        <span className="mt-1 block text-xs text-[var(--studio-text-subtle)]">
                          {outcome.passed} passed · {outcome.failed} failed · {outcome.error} error
                          {' · '}{outcome.judged}/{outcome.total} judged
                        </span>
                      </td>
                      <td className="px-3 py-3"><EvaluationStatusBadge status={run.status} /></td>
                      <td className="px-3 py-3 text-xs text-[var(--studio-text-muted)]">
                        {new Date(run.created_at).toLocaleString()}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <nav aria-label="Evaluation run pages" className="flex flex-wrap items-center justify-between gap-3">
            <div>
              {query.cursor !== undefined && (
                <AppLink to={evaluationRunsPath({ ...query, cursor: undefined })}>
                  First page
                </AppLink>
              )}
            </div>
            {request.data.next_cursor !== null && (
              <AppLink
                to={evaluationRunsPath({
                  ...query,
                  cursor: request.data.next_cursor,
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
