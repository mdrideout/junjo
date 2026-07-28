import { getApiHost } from '../../../config'
import {
  EvaluationIdSchema,
  EvaluationRunDetailSchema,
  type EvaluationRunDetail,
} from '../schemas/evaluation-runs'

export async function getEvaluationRun(runId: string): Promise<EvaluationRunDetail> {
  const validatedRunId = EvaluationIdSchema.parse(runId)
  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation/runs/${encodeURIComponent(validatedRunId)}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation run (${response.status})`)
  }
  return EvaluationRunDetailSchema.parse(await response.json())
}
