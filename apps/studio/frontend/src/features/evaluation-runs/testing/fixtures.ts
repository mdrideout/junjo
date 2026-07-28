import type {
  EvaluationAttemptStatus,
  EvaluationRunDetail,
  EvaluationRunListItem,
  EvaluationRunListPage,
} from '../schemas/evaluation-runs'

const RECORDED_AT = '2026-07-27T16:30:00Z'

interface DetailFixtureOptions {
  runId?: string
  datasetId?: string
  candidateLabel?: string
  sourceRevision?: string
  attemptStatuses?: EvaluationAttemptStatus[]
}

export function makeEvaluationRunDetailFixture({
  runId = 'eval-run-baseline',
  datasetId = 'eval-dataset-local-places',
  candidateLabel = 'baseline',
  sourceRevision = '1111111111111111111111111111111111111111',
  attemptStatuses = ['passed', 'failed', 'error', 'queued'],
}: DetailFixtureOptions = {}): EvaluationRunDetail {
  const runCompleted = !attemptStatuses.includes('queued')
  return {
    run: {
      id: runId,
      dataset_id: datasetId,
      request_key: `${runId}-request`,
      candidate_label: candidateLabel,
      source_revision: sourceRevision,
      status: runCompleted ? 'completed' : 'active',
      created_by_user_id: 'user-evaluation-fixture',
      created_at: '2026-07-27T16:00:00Z',
      completed_at: runCompleted ? RECORDED_AT : null,
    },
    dataset: {
      id: datasetId,
      application_key: 'ai_chat',
      key: 'local-places',
      name: 'Local places',
      description: 'Small locked evaluation corpus.',
      status: 'locked',
      created_by_user_id: 'user-evaluation-fixture',
      created_at: '2026-07-27T15:00:00Z',
      locked_at: '2026-07-27T15:30:00Z',
    },
    cases: attemptStatuses.map((status, index) => {
      const ordinal = index + 1
      const generated = index === 0
      const terminal = status !== 'queued'
      const score = status === 'passed' ? 0.9 : status === 'failed' ? 0.25 : null
      const reason =
        status === 'passed'
          ? 'The response satisfies the requested local-place criteria.'
          : status === 'failed'
            ? 'The response omitted a required local detail.'
            : status === 'error'
              ? 'The evaluator could not produce a valid judgment.'
              : null
      const subjectExecution = terminal
        ? {
            service_namespace: '',
            service_name: 'ai-chat-evaluation',
            executable_type: 'workflow' as const,
            runtime_id: `${runId}-runtime-${ordinal}`,
          }
        : null
      return {
        case: {
          id: `${datasetId}-case-${ordinal}`,
          dataset_id: datasetId,
          case_key: `local-place-${ordinal}`,
          ordinal,
          origin: generated ? 'generated' : 'authored',
          target_kind: ordinal === 1 ? 'workflow' : 'node',
          target_key: ordinal === 1 ? 'turn_workflow' : 'date_response_node',
          input_version: 1,
          input_json: { location: `Place ${ordinal}` },
          expectation_json: { should_mention_location: true },
          evaluator_key: 'qualitative_response',
          evaluator_version: 1,
          source_execution: generated
            ? {
                service_namespace: 'junjo.examples',
                service_name: 'ai-chat',
                executable_type: 'workflow',
                runtime_id: `source-runtime-${ordinal}`,
              }
            : null,
          source_revision: generated
            ? 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            : null,
          created_at: '2026-07-27T15:10:00Z',
        },
        attempt: {
          id: `${runId}-attempt-${ordinal}`,
          run_id: runId,
          case_id: `${datasetId}-case-${ordinal}`,
          status,
          score,
          reason,
          duration_ms: terminal ? ordinal * 100 : null,
          subject_execution: subjectExecution,
          execution_bound_at: subjectExecution === null ? null : '2026-07-27T16:10:00Z',
          recorded_at: terminal ? RECORDED_AT : null,
        },
      }
    }),
  }
}

export function makeEvaluationRunListItem(
  detail: EvaluationRunDetail,
): EvaluationRunListItem {
  const attemptCounts = {
    total: detail.cases.length,
    queued: 0,
    passed: 0,
    failed: 0,
    error: 0,
  }
  for (const item of detail.cases) {
    attemptCounts[item.attempt.status] += 1
  }
  return {
    run: detail.run,
    dataset: {
      id: detail.dataset.id,
      application_key: detail.dataset.application_key,
      key: detail.dataset.key,
      name: detail.dataset.name,
      status: detail.dataset.status,
    },
    attempt_counts: attemptCounts,
  }
}

export function makeEvaluationRunListPage(
  details: EvaluationRunDetail[],
  nextCursor: string | null = null,
): EvaluationRunListPage {
  return {
    items: details.map(makeEvaluationRunListItem),
    next_cursor: nextCursor,
  }
}
