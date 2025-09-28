import { z } from 'zod'
import { API_HOST } from '../../../../config'
import { OtelSpan, OtelSpanSchema } from '../../../otel/schemas/schemas'

/**
 * Get Spans - Type Workflow
 * Fetches all spans where the type is a junjo workflow.
 * @returns
 */
export async function getSpansTypeWorkflow(): Promise<OtelSpan[]> {
  const response = await fetch(`${API_HOST}/otel/spans/type/workflow`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch workflow executions')
  }

  const data = await response.json()
  const validatedData = z.array(OtelSpanSchema).parse(data)
  return validatedData
}
