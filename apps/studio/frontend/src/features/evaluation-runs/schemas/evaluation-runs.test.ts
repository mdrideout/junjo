import { describe, expect, it } from 'vitest'
import {
  EvaluationRunDetailSchema,
  EvaluationRunListPageSchema,
  SemanticExecutionReferenceSchema,
} from './evaluation-runs'
import {
  EvaluationRunComparisonQuerySchema,
  evaluationRunListQueryFromSearchParams,
} from './query'
import {
  makeEvaluationRunDetailFixture,
  makeEvaluationRunListPage,
} from '../testing/fixtures'

describe('evaluation run schemas', () => {
  it('parses the bounded list and ordered detail response contracts', () => {
    const detail = makeEvaluationRunDetailFixture()
    expect(EvaluationRunDetailSchema.parse(detail)).toEqual(detail)
    expect(EvaluationRunListPageSchema.parse(makeEvaluationRunListPage([detail], 'next-page'))).toBeDefined()
  })

  it('requires an exact semantic execution identity', () => {
    const reference = {
      service_namespace: '',
      service_name: 'ai-chat-evaluation',
      executable_type: 'workflow',
      runtime_id: 'workflow-run',
    }
    expect(SemanticExecutionReferenceSchema.parse(reference)).toEqual(reference)
    expect(
      SemanticExecutionReferenceSchema.safeParse({
        ...reference,
        executable_type: 'node',
      }).success,
    ).toBe(false)
    expect(
      SemanticExecutionReferenceSchema.safeParse({
        ...reference,
        trace_id: 'not-part-of-the-semantic-reference',
      }).success,
    ).toBe(false)
  })

  it('parses cursor pagination from the URL and rejects invalid comparisons', () => {
    expect(
      evaluationRunListQueryFromSearchParams(
        new URLSearchParams('dataset_id=dataset-1&cursor=opaque%2Fcursor&limit=25'),
      ),
    ).toEqual({
      dataset_id: 'dataset-1',
      cursor: 'opaque/cursor',
      limit: 25,
    })
    expect(
      evaluationRunListQueryFromSearchParams(new URLSearchParams('limit=101')),
    ).toBeNull()
    expect(
      EvaluationRunComparisonQuerySchema.safeParse({
        baseline_run_id: 'same-run',
        candidate_run_id: 'same-run',
      }).success,
    ).toBe(false)
  })
})
