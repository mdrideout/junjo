import { WorkflowMetadataResponseSchema, WorkflowMetadatum } from '../schemas'

/**
 * Fetch Workflow Metadata
 *
 * Returns a list of workflow metadata (workflows that have run).
 * @param exec_id
 * @returns
 */
export const fetchWorkflowMetadata = async (): Promise<WorkflowMetadatum[]> => {
  const response = await fetch(`http://localhost:1323/workflow-metadata`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch workflow metadata: ${response.statusText}`)
  }

  const data = await response.json()
  console.log('Received data: ', data)

  // Validate the response data against our schema
  try {
    return WorkflowMetadataResponseSchema.parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
