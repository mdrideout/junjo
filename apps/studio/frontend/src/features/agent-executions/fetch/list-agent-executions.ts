import { getApiHost } from '../../../config'
import {
  AgentExecutionSummaryListSchema,
  type AgentExecutionSummary,
} from '../schemas/agent-execution'
import { AgentExecutionQuerySchema, type AgentExecutionQuery } from '../schemas/query'
import { getAgentEvidenceErrorMessage } from './semantic-error'

export async function listAgentExecutions(query: AgentExecutionQuery): Promise<AgentExecutionSummary[]> {
  const validated = AgentExecutionQuerySchema.parse(query)
  const parameters = new URLSearchParams()

  parameters.set('service_namespace', validated.service_namespace)
  parameters.set('service_name', validated.service_name)

  if (validated.agent_key !== undefined) parameters.set('agent_key', validated.agent_key)
  if (validated.structural_id !== undefined) parameters.set('structural_id', validated.structural_id)
  if (validated.service_version !== undefined) parameters.set('service_version', validated.service_version)
  if (validated.outcome !== undefined) parameters.set('outcome', validated.outcome)
  if (validated.start_time !== undefined) parameters.set('start_time', validated.start_time)
  if (validated.end_time !== undefined) parameters.set('end_time', validated.end_time)
  if (validated.limit !== undefined) parameters.set('limit', String(validated.limit))

  const response = await fetch(`${getApiHost()}/api/v1/agent-executions?${parameters.toString()}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(await getAgentEvidenceErrorMessage(response, 'Failed to fetch Agent executions'))
  }

  return AgentExecutionSummaryListSchema.parse(await response.json())
}
