import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../../root-store/store'
import type {
  EvaluationAttempt,
  EvaluationCase,
  EvaluationDataset,
  EvaluationDatasetDetail,
  EvaluationDatasetListPage,
  EvaluationRun,
  EvaluationRunDetail,
  EvaluationRunListPage,
} from '../schemas/evaluation-runs'
import type { EvaluationRunComparisonQuery, EvaluationRunListQuery } from '../schemas/query'
import { getEvaluationRunListQueryKey } from '../schemas/query'
import type { EvaluationRequestState } from './slice'

const EMPTY_LIST_REQUEST: EvaluationRequestState<EvaluationRunListPage> = {
  data: null,
  loading: false,
  error: null,
}

const EMPTY_DATASET_REQUEST: EvaluationRequestState<EvaluationDatasetListPage> = {
  data: null,
  loading: false,
  error: null,
}

export function selectEvaluationDatasetListRequest(
  state: RootState,
): EvaluationRequestState<EvaluationDatasetListPage> {
  return state.evaluationRunsState.datasets ?? EMPTY_DATASET_REQUEST
}

const EMPTY_RUN_DETAIL_REQUEST: EvaluationRequestState<EvaluationRunDetail> = {
  data: null,
  loading: false,
  error: null,
}

const EMPTY_DATASET_DETAIL_REQUEST: EvaluationRequestState<EvaluationDatasetDetail> = {
  data: null,
  loading: false,
  error: null,
}

export function selectEvaluationDatasetDetailRequest(
  state: RootState,
  datasetId: string,
): EvaluationRequestState<EvaluationDatasetDetail> {
  return state.evaluationRunsState.datasetDetails[datasetId]
    ?? EMPTY_DATASET_DETAIL_REQUEST
}

export function selectEvaluationRunListRequest(
  state: RootState,
  query: EvaluationRunListQuery,
): EvaluationRequestState<EvaluationRunListPage> {
  return state.evaluationRunsState.lists[getEvaluationRunListQueryKey(query)]
    ?? EMPTY_LIST_REQUEST
}

export function selectEvaluationRunDetailRequest(
  state: RootState,
  runId: string,
): EvaluationRequestState<EvaluationRunDetail> {
  return state.evaluationRunsState.details[runId] ?? EMPTY_RUN_DETAIL_REQUEST
}

export interface EvaluationRunComparisonRow {
  case: EvaluationCase
  baseline_attempt: EvaluationAttempt
  candidate_attempt: EvaluationAttempt
  transition: EvaluationTransition
  duration_delta_ms: number | null
}

export type EvaluationTransition =
  | 'improved'
  | 'regressed'
  | 'newly_errored'
  | 'recovered'
  | 'unchanged'
  | 'changed'

export interface EvaluationComparisonSummary {
  total: number
  judged: number
  passed: number
  failed: number
  error: number
  queued: number
  pass_rate: number | null
}

export interface EvaluationRunComparison {
  dataset: EvaluationDataset
  baseline_run: EvaluationRun
  candidate_run: EvaluationRun
  baseline_summary: EvaluationComparisonSummary
  candidate_summary: EvaluationComparisonSummary
  transition_counts: Record<EvaluationTransition, number>
  rows: EvaluationRunComparisonRow[]
}

export interface EvaluationRunComparisonResult {
  data: EvaluationRunComparison | null
  error: string | null
}

function attemptTransition(
  baseline: EvaluationAttempt,
  candidate: EvaluationAttempt,
): EvaluationTransition {
  if (baseline.status === 'failed' && candidate.status === 'passed') return 'improved'
  if (baseline.status === 'passed' && candidate.status === 'failed') return 'regressed'
  if (baseline.status !== 'error' && candidate.status === 'error') return 'newly_errored'
  if (baseline.status === 'error' && candidate.status !== 'error') return 'recovered'
  if (baseline.status === candidate.status) {
    return 'unchanged'
  }
  return 'changed'
}

function comparisonSummary(attempts: EvaluationAttempt[]): EvaluationComparisonSummary {
  const summary = {
    total: attempts.length,
    judged: 0,
    passed: 0,
    failed: 0,
    error: 0,
    queued: 0,
    pass_rate: null as number | null,
  }
  for (const attempt of attempts) summary[attempt.status] += 1
  summary.judged = summary.passed + summary.failed
  summary.pass_rate = summary.judged === 0 ? null : summary.passed / summary.judged
  return summary
}

function caseMatchesComparisonScope(
  item: EvaluationCase,
  scope: EvaluationRunComparisonQuery,
): boolean {
  return (
    (scope.target_kind === undefined || item.target_kind === scope.target_kind)
    && (scope.target_key === undefined || item.target_key === scope.target_key)
    && (scope.input_version === undefined || item.input_version === scope.input_version)
    && (
      scope.evaluation_name === undefined
      || item.evaluation_name === scope.evaluation_name
    )
  )
}

export function projectEvaluationRunComparison(
  baseline: EvaluationRunDetail,
  candidate: EvaluationRunDetail,
  scope: EvaluationRunComparisonQuery = {
    baseline_run_id: baseline.run.id,
    candidate_run_id: candidate.run.id,
  },
): EvaluationRunComparisonResult {
  if (baseline.dataset.id !== candidate.dataset.id) {
    return { data: null, error: 'Evaluation runs must use the same locked dataset.' }
  }

  const candidateCases = new Map(candidate.cases.map((item) => [item.case.id, item]))
  if (candidateCases.size !== baseline.cases.length || candidate.cases.length !== baseline.cases.length) {
    return { data: null, error: 'Evaluation runs do not contain the same case membership.' }
  }

  const rows: EvaluationRunComparisonRow[] = []
  for (const baselineItem of [...baseline.cases].sort(
    (left, right) => left.case.ordinal - right.case.ordinal,
  )) {
    const candidateItem = candidateCases.get(baselineItem.case.id)
    if (candidateItem === undefined) {
      return { data: null, error: 'Evaluation runs do not contain the same case membership.' }
    }
    if (!caseMatchesComparisonScope(baselineItem.case, scope)) continue
    const baselineAttempt = baselineItem.attempt
    const candidateAttempt = candidateItem.attempt
    rows.push({
      case: baselineItem.case,
      baseline_attempt: baselineAttempt,
      candidate_attempt: candidateAttempt,
      transition: attemptTransition(baselineAttempt, candidateAttempt),
      duration_delta_ms:
        baselineAttempt.duration_ms === null || candidateAttempt.duration_ms === null
          ? null
          : candidateAttempt.duration_ms - baselineAttempt.duration_ms,
    })
  }

  const transitionCounts: Record<EvaluationTransition, number> = {
    improved: 0,
    regressed: 0,
    newly_errored: 0,
    recovered: 0,
    unchanged: 0,
    changed: 0,
  }
  for (const row of rows) transitionCounts[row.transition] += 1

  return {
    data: {
      dataset: baseline.dataset,
      baseline_run: baseline.run,
      candidate_run: candidate.run,
      baseline_summary: comparisonSummary(
        rows.map((row) => row.baseline_attempt),
      ),
      candidate_summary: comparisonSummary(
        rows.map((row) => row.candidate_attempt),
      ),
      transition_counts: transitionCounts,
      rows,
    },
    error: null,
  }
}

export const selectEvaluationRunComparison = createSelector(
  [
    (state: RootState) => state.evaluationRunsState.details,
    (_state: RootState, query: EvaluationRunComparisonQuery) => query,
  ],
  (details, query): EvaluationRunComparisonResult => {
    const { baseline_run_id: baselineRunId, candidate_run_id: candidateRunId } = query
    const baseline = details[baselineRunId]?.data
    const candidate = details[candidateRunId]?.data
    if (
      baseline === null
      || baseline === undefined
      || candidate === null
      || candidate === undefined
    ) {
      return { data: null, error: null }
    }
    return projectEvaluationRunComparison(baseline, candidate, query)
  },
)
