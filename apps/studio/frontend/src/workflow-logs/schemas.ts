import { z } from 'zod'

// Zod schema for workflow log validation
export const WorkflowLogSchema = z.object({
  ID: z.string(),
  ExecID: z.string(),
  Type: z.string(),
  EventTimeNano: z.number(),
  IngestionTime: z.string(),
  State: z.any(),
})
export type WorkflowLog = z.infer<typeof WorkflowLogSchema>

// Schema for multiple logs / response
export const WorkflowLogsResponseSchema = z.array(WorkflowLogSchema)

// Zod schema for workflow metadata validation
export const WorkflowMetadatumSchema = z.object({
  ID: z.string(),
  ExecID: z.string(),
  Name: z.string(),
  CreatedAt: z.string(), // Time values come as ISO strings from the API
  Structure: z.any(), // Using any for the interface{} equivalent
})
export type WorkflowMetadatum = z.infer<typeof WorkflowMetadatumSchema>

// Schema for multiple metadata / response
export const WorkflowMetadataListResponseSchema = z.array(WorkflowMetadatumSchema)
