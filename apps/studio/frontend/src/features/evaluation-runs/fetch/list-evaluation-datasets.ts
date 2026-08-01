import { getApiHost } from '../../../config'
import {
  EvaluationDatasetListPageSchema,
  type EvaluationDatasetListPage,
} from '../schemas/evaluation-runs'

export async function listEvaluationDatasets(): Promise<EvaluationDatasetListPage> {
  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation/datasets?limit=100`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation datasets (${response.status})`)
  }
  return EvaluationDatasetListPageSchema.parse(await response.json())
}
