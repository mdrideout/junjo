import { getApiHost } from '../../../config'
import {
  EvaluationTokenReadSchema,
  type EvaluationTokenRead,
} from '../schemas'

export async function revokeEvaluationToken(
  tokenId: string,
): Promise<EvaluationTokenRead> {
  const response = await fetch(
    `${getApiHost()}/api/v1/evaluation-tokens/${encodeURIComponent(tokenId)}/revoke`,
    {
      method: 'PUT',
      credentials: 'include',
    },
  )
  if (!response.ok) {
    throw new Error(`Failed to revoke evaluation token (${response.status})`)
  }
  return EvaluationTokenReadSchema.parse(await response.json())
}
