import { z } from 'zod'
import { AgentOutcomeSchema } from './agent-execution'

export const AgentExecutionQuerySchema = z
  .object({
    service_namespace: z.string(),
    service_name: z.string().min(1),
    agent_key: z.string().min(1).optional(),
    structural_id: z.string().min(1).optional(),
    service_version: z.string().min(1).optional(),
    outcome: AgentOutcomeSchema.optional(),
    start_time: z.string().datetime({ offset: true }).optional(),
    end_time: z.string().datetime({ offset: true }).optional(),
    limit: z.number().int().positive().max(250).optional(),
  })
  .strict()
  .superRefine((query, context) => {
    if (
      query.start_time !== undefined
      && query.end_time !== undefined
      && Date.parse(query.start_time) > Date.parse(query.end_time)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_time'],
        message: 'end_time must be later than or equal to start_time',
      })
    }
  })

export type AgentExecutionQuery = z.infer<typeof AgentExecutionQuerySchema>

export function getAgentExecutionQueryKey(query: AgentExecutionQuery): string {
  const validated = AgentExecutionQuerySchema.parse(query)
  return JSON.stringify(validated)
}

export function getAgentExecutionDetailKey(traceId: string, agentSpanId: string): string {
  return `${traceId}:${agentSpanId}`
}
