import { z } from 'zod'
import { API_HOST } from '../../../../config'
import { OtelSpan, OtelSpanSchema } from '../../../otel/schemas/schemas'

const GetWorkflowExecutionsResponseSchema = z.array(OtelSpanSchema)

export async function getWorkflowExecutions(): Promise<OtelSpan[]> {
  const response = await fetch(`${API_HOST}/otel/workflow-executions`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch workflow executions')
  }

  const data = await response.json()
  const validatedData = GetWorkflowExecutionsResponseSchema.parse(data)
  return validatedData
}
