import { z } from 'zod'

export const ExecutableTypeSchema = z.enum(['workflow', 'subflow', 'agent'])
export type ExecutableType = z.infer<typeof ExecutableTypeSchema>

export const ExecutionResolutionRequestSchema = z.object({
  service_namespace: z.string(),
  service_name: z.string().min(1),
  executable_type: ExecutableTypeSchema,
  runtime_id: z.string().min(1),
  destination: z.enum(['detail', 'trace']),
}).strict()
export type ExecutionResolutionRequest = z.infer<typeof ExecutionResolutionRequestSchema>

export const ExecutionResolutionSchema = z.object({
  service_namespace: z.string(),
  service_name: z.string().min(1),
  executable_type: ExecutableTypeSchema,
  runtime_id: z.string().min(1),
  trace_id: z.string().regex(/^[0-9a-f]{32}$/),
  span_id: z.string().regex(/^[0-9a-f]{16}$/),
  detail_path: z.string().startsWith('/'),
  trace_path: z.string().startsWith('/'),
}).strict()
export type ExecutionResolution = z.infer<typeof ExecutionResolutionSchema>

export const ExecutionResolutionConflictSchema = z.object({
  code: z.literal('ambiguous_execution_identity'),
  message: z.string().min(1),
  match_count: z.number().int().min(2),
}).strict()
