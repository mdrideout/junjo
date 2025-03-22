// import { WorkflowLog, WorkflowLogsResponseSchema } from '../schemas'

// export const fetchWorkflowLogs = async (exec_id: string): Promise<WorkflowLog[]> => {
//   const response = await fetch(`http://localhost:1323/workflow-logs/${exec_id}`, {
//     method: 'GET',
//     credentials: 'include',
//     headers: {
//       Accept: 'application/json',
//     },
//   })

//   if (!response.ok) {
//     throw new Error(`Failed to fetch workflow logs: ${response.statusText}`)
//   }

//   const data = await response.json()

//   // Validate the response data against our schema
//   try {
//     return WorkflowLogsResponseSchema.parse(data)
//   } catch (error) {
//     console.error('Data validation error:', error)
//     throw new Error('Invalid data received from server')
//   }
// }
