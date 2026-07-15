import { getApiHost } from '../../../config'
import {
  ExecutionResolutionConflictSchema,
  ExecutionResolutionRequestSchema,
  ExecutionResolutionSchema,
  type ExecutionResolution,
  type ExecutionResolutionRequest,
} from '../schemas'

export async function resolveExecution(
  request: ExecutionResolutionRequest,
  signal?: AbortSignal,
): Promise<ExecutionResolution | null> {
  const validated = ExecutionResolutionRequestSchema.parse(request)
  const parameters = new URLSearchParams({
    service_namespace: validated.service_namespace,
    service_name: validated.service_name,
    executable_type: validated.executable_type,
    runtime_id: validated.runtime_id,
  })
  const response = await fetch(
    `${getApiHost()}/api/v1/execution-resolution?${parameters.toString()}`,
    { credentials: 'include', signal },
  )
  if (response.status === 404) return null
  if (response.status === 409) {
    const conflict = ExecutionResolutionConflictSchema.parse(await response.json())
    throw new Error(`${conflict.message} (${conflict.match_count} matches)`)
  }
  if (!response.ok) {
    throw new Error(`Studio could not resolve the execution (${response.status}).`)
  }
  return ExecutionResolutionSchema.parse(await response.json())
}
