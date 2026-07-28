import { getApiHost } from '../../../config'
import {
  EvaluationTokenListSchema,
  type EvaluationTokenList,
} from '../schemas'

export async function listEvaluationTokens(
  cursor?: string,
): Promise<EvaluationTokenList> {
  const parameters = new URLSearchParams({ limit: '50' })
  if (cursor !== undefined) parameters.set('cursor', cursor)
  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation-tokens?${parameters.toString()}`,
    { credentials: 'include' },
  )
  if (!response.ok) {
    throw new Error(`Failed to list evaluation tokens (${response.status})`)
  }
  return EvaluationTokenListSchema.parse(await response.json())
}
