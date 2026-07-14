import { getApiHost } from '../../../config'
import {
  AgentExecutionDetailSchema,
  SpanIdSchema,
  TraceIdSchema,
  type AgentExecutionDetail,
} from '../schemas/agent-execution'
import { getAgentEvidenceErrorMessage } from './semantic-error'

export async function getAgentExecution(traceId: string, agentSpanId: string): Promise<AgentExecutionDetail> {
  const validatedTraceId = TraceIdSchema.parse(traceId)
  const validatedAgentSpanId = SpanIdSchema.parse(agentSpanId)

  const endpoint = `/api/v1/agent-executions/${validatedTraceId}/${validatedAgentSpanId}`
  const response = await fetch(`${getApiHost()}${endpoint}`, { credentials: 'include' })

  if (!response.ok) {
    throw new Error(await getAgentEvidenceErrorMessage(response, 'Failed to fetch Agent execution'))
  }

  return AgentExecutionDetailSchema.parse(await response.json())
}
