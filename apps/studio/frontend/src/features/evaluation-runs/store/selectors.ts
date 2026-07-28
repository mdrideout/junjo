import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../../root-store/store'
import type {
  EvaluationAttempt,
  EvaluationCase,
  EvaluationDatasetDetail,
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

const EMPTY_DETAIL_REQUEST: EvaluationRequestState<EvaluationRunDetail> = {
  data: null,
  loading: false,
  error: null,
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
  return state.evaluationRunsState.details[runId] ?? EMPTY_DETAIL_REQUEST
}

export interface EvaluationRunComparisonRow {
  case: EvaluationCase
  baseline_attempt: EvaluationAttempt
  candidate_attempt: EvaluationAttempt
  score_delta: number | null
  duration_delta_ms: number | null
}

export interface EvaluationRunComparison {
  dataset: EvaluationDatasetDetail
  baseline_run: EvaluationRun
  candidate_run: EvaluationRun
  rows: EvaluationRunComparisonRow[]
}

export interface EvaluationRunComparisonResult {
  data: EvaluationRunComparison | null
  error: string | null
}

export function projectEvaluationRunComparison(
  baseline: EvaluationRunDetail,
  candidate: EvaluationRunDetail,
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
    const baselineAttempt = baselineItem.attempt
    const candidateAttempt = candidateItem.attempt
    rows.push({
      case: baselineItem.case,
      baseline_attempt: baselineAttempt,
      candidate_attempt: candidateAttempt,
      score_delta:
        baselineAttempt.score === null || candidateAttempt.score === null
          ? null
          : candidateAttempt.score - baselineAttempt.score,
      duration_delta_ms:
        baselineAttempt.duration_ms === null || candidateAttempt.duration_ms === null
          ? null
          : candidateAttempt.duration_ms - baselineAttempt.duration_ms,
    })
  }

  return {
    data: {
      dataset: baseline.dataset,
      baseline_run: baseline.run,
      candidate_run: candidate.run,
      rows,
    },
    error: null,
  }
}

export const selectEvaluationRunComparison = createSelector(
  [
    (state: RootState) => state.evaluationRunsState.details,
    (_state: RootState, query: EvaluationRunComparisonQuery) => query.baseline_run_id,
    (_state: RootState, query: EvaluationRunComparisonQuery) => query.candidate_run_id,
  ],
  (details, baselineRunId, candidateRunId): EvaluationRunComparisonResult => {
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
    return projectEvaluationRunComparison(baseline, candidate)
  },
)
