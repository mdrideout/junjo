import { getApiHost } from '../../../config'
import {
  EvaluationTokenCreateSchema,
  EvaluationTokenReadSchema,
  type EvaluationTokenCreate,
  type EvaluationTokenRead,
} from '../schemas'

export async function createEvaluationToken(
  request: EvaluationTokenCreate,
): Promise<EvaluationTokenRead> {
  const payload = EvaluationTokenCreateSchema.parse(request)
  const response = await fetch(`${getApiHost()}/api/v1/evaluation-tokens`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error(`Failed to create access token (${response.status})`)
  }
  return EvaluationTokenReadSchema.parse(await response.json())
}
