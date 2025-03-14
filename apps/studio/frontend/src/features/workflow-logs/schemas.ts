import { z } from 'zod'

// Zod schema for workflow log validation
export const WorkflowLogSchema = z.object({
  ID: z.string(),
  ExecID: z.string(),
  Type: z.string(),
  EventTimeNano: z.number(),
  IngestionTime: z.string(), // ISO string
  State: z.string(), // Provided as a base64 encoded JSON string
})
export type WorkflowLog = z.infer<typeof WorkflowLogSchema>

// Schema for multiple logs / response
export const WorkflowLogsResponseSchema = z.array(WorkflowLogSchema)

// Zod schema for node log validation
export const NodeLogSchema = z.object({
  ID: z.string(),
  ExecID: z.string(),
  Type: z.string(),
  EventTimeNano: z.number(),
  IngestionTime: z.string(), // ISO string
  State: z.string(), // Provided as a base64 encoded JSON string
})
export type NodeLog = z.infer<typeof NodeLogSchema>

// Schema for multiple logs / response
export const NodeLogsResponseSchema = z.array(NodeLogSchema)

// Zod schema for workflow metadata validation
export const WorkflowMetadatumSchema = z.object({
  ID: z.string(),
  ExecID: z.string(),
  AppName: z.string(),
  WorkflowName: z.string(),
  EventTimeNano: z.number(),
  IngestionTime: z.string(), // ISO string
  Structure: z.string(), // Provided as a base64 encoded JSON string
})
export type WorkflowMetadatum = z.infer<typeof WorkflowMetadatumSchema>

// Schema for multiple metadata / response
export const WorkflowMetadataListResponseSchema = z.array(WorkflowMetadatumSchema)
