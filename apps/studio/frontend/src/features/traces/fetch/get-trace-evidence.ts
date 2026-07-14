import { getApiHost } from '../../../config'
import { TraceEvidenceSchema, type TraceEvidence } from '../schemas/trace-evidence'
import { TraceIdSchema } from '../../agent-executions/schemas/agent-execution'

export async function getTraceEvidence(traceId: string): Promise<TraceEvidence> {
  const validatedTraceId = TraceIdSchema.parse(traceId)
  const response = await fetch(`${getApiHost()}/api/v1/trace-evidence/${validatedTraceId}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch trace evidence (${response.status})`)
  }

  return TraceEvidenceSchema.parse(await response.json())
}
