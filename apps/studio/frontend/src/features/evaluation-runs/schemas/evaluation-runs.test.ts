import { describe, expect, it } from 'vitest'
import {
  EvaluationRunDetailSchema,
  EvaluationRunListPageSchema,
  OpenTelemetrySpanReferenceSchema,
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
      kind: 'junjo_execution' as const,
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

  it('requires an exact OpenTelemetry span evidence identity', () => {
    const reference = {
      kind: 'otel_span' as const,
      service_namespace: 'junjo.examples',
      service_name: 'base-openai-agents',
      trace_id: '1'.repeat(32),
      span_id: 'a'.repeat(16),
    }
    expect(OpenTelemetrySpanReferenceSchema.parse(reference)).toEqual(reference)
    expect(
      OpenTelemetrySpanReferenceSchema.safeParse({
        ...reference,
        trace_id: 'not-a-trace-id',
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
