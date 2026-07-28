import { getApiHost } from '../../../config'
import {
  EvaluationRunListPageSchema,
  type EvaluationRunListPage,
} from '../schemas/evaluation-runs'
import {
  EvaluationRunListQuerySchema,
  type EvaluationRunListQuery,
} from '../schemas/query'

export async function listEvaluationRuns(
  query: EvaluationRunListQuery,
): Promise<EvaluationRunListPage> {
  const validated = EvaluationRunListQuerySchema.parse(query)
  const parameters = new URLSearchParams({ limit: String(validated.limit) })
  if (validated.dataset_id !== undefined) parameters.set('dataset_id', validated.dataset_id)
  if (validated.cursor !== undefined) parameters.set('cursor', validated.cursor)

  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation/runs?${parameters.toString()}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation runs (${response.status})`)
  }
  return EvaluationRunListPageSchema.parse(await response.json())
}
