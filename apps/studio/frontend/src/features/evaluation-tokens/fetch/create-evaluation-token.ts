import { getApiHost } from '../../../config'
import {
  EvaluationTokenCreateSchema,
  EvaluationTokenCreatedSchema,
  type EvaluationTokenCreate,
  type EvaluationTokenCreated,
} from '../schemas'

export async function createEvaluationToken(
  request: EvaluationTokenCreate,
): Promise<EvaluationTokenCreated> {
  const payload = EvaluationTokenCreateSchema.parse(request)
  const response = await fetch(`${getApiHost()}/api/v1/evaluation-tokens`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to create evaluation token (${response.status})`)
  }
  return EvaluationTokenCreatedSchema.parse(await response.json())
}
