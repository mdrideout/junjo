import { z } from 'zod'
import { API_HOST } from '../../../../config'
import { OtelSpan, OtelSpanSchema } from '../../../traces/schemas/schemas'

/**
 * Get Spans - Type Workflow
 * Fetches all spans where the type is a junjo workflow for a specific service.
 * @param serviceName - The service name to filter by
 * @returns
 */
export async function getSpansTypeWorkflow(serviceName: string): Promise<OtelSpan[]> {
  const response = await fetch(`${API_HOST}/otel/spans/type/workflow/${serviceName}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch workflow executions')
  }

  const data = await response.json()
  const validatedData = z.array(OtelSpanSchema).parse(data)
  return validatedData
}
