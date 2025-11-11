import { z } from 'zod'
import { getApiHost } from '../../../../config'
import { OtelSpan, OtelSpanSchema } from '../../../traces/schemas/schemas'

/**
 * Get Spans - Type Workflow
 * Fetches all spans where the type is a junjo workflow for a specific service.
 * @param serviceName - The service name to filter by
 * @returns
 */
export async function getSpansTypeWorkflow(serviceName: string): Promise<OtelSpan[]> {
  // Use Python backend endpoint
  const endpoint = `/api/v1/observability/services/${serviceName}/workflows`
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch workflow executions')
  }

  const data = await response.json()
  const validatedData = z.array(OtelSpanSchema).parse(data)
  return validatedData
}
