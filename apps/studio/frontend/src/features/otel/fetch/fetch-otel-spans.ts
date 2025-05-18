import { WorkflowSpansE2EResponse, WorkflowSpansE2EResponseSchema } from '../schemas/schemas'

export const fetchOtelSpans = async (serviceName: string): Promise<WorkflowSpansE2EResponse> => {
  const response = await fetch(`http://localhost:1323/workflow-spans-e2e/${serviceName}`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`fetchOtelSpans failed: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the data is an array of strings
    return WorkflowSpansE2EResponseSchema.parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
