import { z } from 'zod'
import { OtelSpan, OtelSpanSchema } from '../../traces/schemas/schemas'
import { getApiHost } from '../../../config'

const GetTraceSpansResponseSchema = z.array(OtelSpanSchema)

export async function getTraceSpans(traceId: string): Promise<OtelSpan[]> {
  // Use Python backend endpoint
  const endpoint = `/api/v1/observability/traces/${traceId}/spans`
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch spans')
  }

  const data = await response.json()
  const validatedData = GetTraceSpansResponseSchema.parse(data)
  return validatedData
}
