// import { WorkflowMetadataListResponseSchema, WorkflowMetadatum, WorkflowMetadatumSchema } from '../schemas'

// /**
//  * Fetch Workflow Metadata List
//  *
//  * Returns a list of workflow metadata (workflows that have run).
//  * @returns
//  */
// export const fetchWorkflowMetadataList = async (AppName: string): Promise<WorkflowMetadatum[]> => {
//   const response = await fetch(`http://localhost:1323/app-names/${AppName}/workflow-executions`, {
//     method: 'GET',
//     credentials: 'include',
//     headers: {
//       Accept: 'application/json',
//     },
//   })

//   if (!response.ok) {
//     throw new Error(`Failed to fetch workflow metadata list: ${response.statusText}`)
//   }

//   const data = await response.json()

//   // Validate the response data against our schema
//   try {
//     return WorkflowMetadataListResponseSchema.parse(data)
//   } catch (error) {
//     console.error('Data validation error:', error)
//     throw new Error('Invalid data received from server')
//   }
// }

// /**
//  * Fetch Workflow Metadata
//  *
//  * Fetches a single workflow metadata object by its execution ID.
//  * @param ExecID
//  * @returns
//  */
// export const fetchWorkflowMetadata = async (ExecID: string): Promise<WorkflowMetadatum> => {
//   const response = await fetch(`http://localhost:1323/workflow-metadata/${ExecID}`, {
//     method: 'GET',
//     credentials: 'include',
//     headers: {
//       Accept: 'application/json',
//     },
//   })

//   if (!response.ok) {
//     throw new Error(`Failed to fetch workflow metadata: ${response.statusText}`)
//   }

//   const data = await response.json()

//   // Validate the response data against our schema
//   try {
//     return WorkflowMetadatumSchema.parse(data)
//   } catch (error) {
//     console.error('Data validation error:', error)
//     throw new Error('Invalid data received from server')
//   }
// }
