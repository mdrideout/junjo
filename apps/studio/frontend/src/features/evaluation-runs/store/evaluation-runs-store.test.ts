import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../../auth/test-utils/mock-server'
import { store, type RootState } from '../../../root-store/store'
import {
  makeEvaluationRunDetailFixture,
  makeEvaluationRunListPage,
} from '../testing/fixtures'
import {
  projectEvaluationRunComparison,
  selectEvaluationRunDetailRequest,
  selectEvaluationRunListRequest,
} from './selectors'
import {
  EvaluationRunsActions,
  evaluationRunsReducer,
  initialEvaluationRunsState,
} from './slice'
import { getEvaluationRunListQueryKey } from '../schemas/query'

describe('evaluation run state', () => {
  it('stores list and detail requests independently', () => {
    const detail = makeEvaluationRunDetailFixture()
    const query = { dataset_id: detail.dataset.id, limit: 50 }
    const listKey = getEvaluationRunListQueryKey(query)
    let featureState = evaluationRunsReducer(
      initialEvaluationRunsState,
      EvaluationRunsActions.setListData({
        key: listKey,
        data: makeEvaluationRunListPage([detail]),
      }),
    )
    featureState = evaluationRunsReducer(
      featureState,
      EvaluationRunsActions.setDetailData({ runId: detail.run.id, data: detail }),
    )
    const root = {
      ...store.getState(),
      evaluationRunsState: featureState,
    } satisfies RootState

    expect(selectEvaluationRunListRequest(root, query).data?.items).toHaveLength(1)
    expect(selectEvaluationRunDetailRequest(root, detail.run.id).data).toEqual(detail)
  })

  it('aligns same-dataset runs by case ID and derives candidate deltas', () => {
    const baseline = makeEvaluationRunDetailFixture({
      runId: 'comparison-baseline',
      attemptStatuses: ['passed', 'failed'],
    })
    const candidateFixture = makeEvaluationRunDetailFixture({
      runId: 'comparison-candidate',
      candidateLabel: 'candidate',
      attemptStatuses: ['passed', 'passed'],
    })
    const candidate = {
      ...candidateFixture,
      cases: candidateFixture.cases.map((item, index) =>
        index === 0
          ? {
              ...item,
              attempt: {
                ...item.attempt,
                score: 1,
                duration_ms: 140,
                reason: 'The candidate is more specific.',
              },
            }
          : item,
      ),
    }
    const result = projectEvaluationRunComparison(baseline, candidate)

    expect(result.error).toBeNull()
    expect(result.data?.rows[0].score_delta).toBeCloseTo(0.1)
    expect(result.data?.rows[0].duration_delta_ms).toBe(40)
    expect(result.data?.rows.map((row) => row.case.id)).toEqual(
      baseline.cases.map((item) => item.case.id),
    )
  })

  it('rejects comparison across different datasets', () => {
    const baseline = makeEvaluationRunDetailFixture({ datasetId: 'dataset-a' })
    const candidate = makeEvaluationRunDetailFixture({
      runId: 'other-run',
      datasetId: 'dataset-b',
    })
    expect(projectEvaluationRunComparison(baseline, candidate)).toEqual({
      data: null,
      error: 'Evaluation runs must use the same locked dataset.',
    })
  })

  it('deduplicates an in-flight list request and stores parsed data', async () => {
    const detail = makeEvaluationRunDetailFixture({ runId: 'listener-list-run' })
    const query = { dataset_id: 'listener-list-dataset', limit: 25 }
    let requestCount = 0
    server.use(
      http.get(`${API_BASE}/api/v1/evaluation/runs`, () => {
        requestCount += 1
        return HttpResponse.json(makeEvaluationRunListPage([detail]))
      }),
    )

    store.dispatch(EvaluationRunsActions.fetchEvaluationRuns(query))
    store.dispatch(EvaluationRunsActions.fetchEvaluationRuns(query))

    await waitFor(() => {
      expect(selectEvaluationRunListRequest(store.getState(), query)).toMatchObject({
        loading: false,
        error: null,
        data: { items: [{ run: { id: detail.run.id } }] },
      })
    })
    expect(requestCount).toBe(1)
  })
})
