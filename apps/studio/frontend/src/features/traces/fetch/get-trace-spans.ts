import { z } from 'zod'
import { OtelSpan, OtelSpanSchema } from '../../traces/schemas/schemas'
import { API_HOST } from '../../../config'

const GetTraceSpansResponseSchema = z.array(OtelSpanSchema)

export async function getTraceSpans(traceId: string): Promise<OtelSpan[]> {
  const response = await fetch(`${API_HOST}/otel/trace/${traceId}/nested-spans`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch spans')
  }

  const data = await response.json()
  const validatedData = GetTraceSpansResponseSchema.parse(data)
  return validatedData
}
