import { NodeLog, NodeLogsResponseSchema } from '../schemas'

export const fetchNodeLogs = async (exec_id: string): Promise<NodeLog[]> => {
  const response = await fetch(`http://localhost:1323/node-logs/${exec_id}`, {
    method: 'GET',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch node logs: ${response.statusText}`)
  }

  const data = await response.json()

  // Validate the response data against our schema
  try {
    return NodeLogsResponseSchema.parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
