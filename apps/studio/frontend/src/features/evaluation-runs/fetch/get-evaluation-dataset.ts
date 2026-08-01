import { getApiHost } from '../../../config'
import {
  EvaluationDatasetDetailSchema,
  EvaluationIdSchema,
  type EvaluationDatasetDetail,
} from '../schemas/evaluation-runs'

export async function getEvaluationDataset(
  datasetId: string,
): Promise<EvaluationDatasetDetail> {
  const validatedDatasetId = EvaluationIdSchema.parse(datasetId)
  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation/datasets/${encodeURIComponent(validatedDatasetId)}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation dataset (${response.status})`)
  }
  return EvaluationDatasetDetailSchema.parse(await response.json())
}
