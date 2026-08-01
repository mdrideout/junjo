import type {
  EvaluationAttemptStatus,
  EvaluationDatasetDetail,
  EvaluationDatasetListPage,
  EvaluationRunDetail,
  EvaluationRunListItem,
  EvaluationRunListPage,
} from '../schemas/evaluation-runs'

const RECORDED_AT = '2026-07-27T16:30:00Z'

interface DetailFixtureOptions {
  runId?: string
  datasetId?: string
  runLabel?: string
  sourceRevision?: string
  attemptStatuses?: EvaluationAttemptStatus[]
}

export function makeEvaluationRunDetailFixture({
  runId = 'eval-run-baseline',
  datasetId = 'eval-dataset-local-places',
  runLabel = 'baseline',
  sourceRevision = '1111111111111111111111111111111111111111',
  attemptStatuses = ['passed', 'failed', 'error', 'queued'],
}: DetailFixtureOptions = {}): EvaluationRunDetail {
  const runCompleted = !attemptStatuses.includes('queued')
  return {
    run: {
      id: runId,
      dataset_id: datasetId,
      request_key: `${runId}-request`,
      run_label: runLabel,
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
          evaluation_name: 'Response place realism',
          ordinal,
          origin: generated ? 'generated' : 'authored',
          target_kind: ordinal === 1 ? 'workflow' : 'node',
          target_key: ordinal === 1 ? 'turn_workflow' : 'date_response_node',
          input_version: 1,
          input_json: { message: `Recommend a real place near Place ${ordinal}.` },
          expectation_json: {
            rubric: 'Mention a real place and keep the geography plausible.',
          },
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
  const judged = attemptCounts.passed + attemptCounts.failed
  const targetCounts = new Map<string, number>()
  const evaluationCounts = new Map<string, number>()
  for (const item of detail.cases) {
    const targetKey = JSON.stringify([
      item.case.target_kind,
      item.case.target_key,
      item.case.input_version,
    ])
    targetCounts.set(targetKey, (targetCounts.get(targetKey) ?? 0) + 1)
    evaluationCounts.set(
      item.case.evaluation_name,
      (evaluationCounts.get(item.case.evaluation_name) ?? 0) + 1,
    )
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
    outcome_summary: {
      ...attemptCounts,
      judged,
      pass_rate: judged === 0 ? null : attemptCounts.passed / judged,
      coverage: attemptCounts.total === 0 ? null : judged / attemptCounts.total,
    },
    target_facets: [...targetCounts].map(([identity, caseCount]) => {
      const [targetKind, targetKey, inputVersion] = JSON.parse(identity) as [
        'node' | 'workflow' | 'agent',
        string,
        number,
      ]
      return {
        target_kind: targetKind,
        target_key: targetKey,
        input_version: inputVersion,
        case_count: caseCount,
      }
    }),
    evaluation_facets: [...evaluationCounts].map(([evaluationName, caseCount]) => ({
      evaluation_name: evaluationName,
      case_count: caseCount,
    })),
  }
}

export function makeEvaluationRunListPage(
  details: EvaluationRunDetail[],
  nextCursor: string | null = null,
): EvaluationRunListPage {
  return {
    scope: {
      dataset_id: details[0]?.dataset.id ?? null,
      target_kind: null,
      target_key: null,
      input_version: null,
      evaluation_name: null,
    },
    items: details.map(makeEvaluationRunListItem),
    next_cursor: nextCursor,
  }
}

export function makeEvaluationDatasetListPage(
  details: EvaluationRunDetail[],
): EvaluationDatasetListPage {
  const datasets = new Map(details.map((detail) => [detail.dataset.id, detail.dataset]))
  return {
    items: [...datasets.values()],
    next_cursor: null,
  }
}

export function makeEvaluationDatasetDetailFixture(
  detail: EvaluationRunDetail = makeEvaluationRunDetailFixture(),
): EvaluationDatasetDetail {
  return {
    dataset: detail.dataset,
    cases: detail.cases.map((item) => item.case),
  }
}
