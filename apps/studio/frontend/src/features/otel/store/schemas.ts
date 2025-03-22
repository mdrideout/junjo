import { z } from 'zod'

export enum JunjoSpanType {
  WORKFLOW = 'workflow',
  NODE = 'node',
}

export const OtelSpanSchema = z.object({
  span_id: z.string(),
  trace_id: z.string(),
  attributes_json: z.record(z.any()),
  start_time: z.string().datetime({ offset: true }),
  end_time: z.string().datetime({ offset: true }),
  events_json: z.array(z.record(z.any())),
  kind: z.string(),
  links_json: z.array(z.record(z.any())),
  name: z.string(),
  parent_span_id: z.string(),
  status_code: z.string(),
  status_message: z.string(),
  trace_flags: z.number(),
  trace_state: z.any(),
  junjo_id: z.string(),
  junjo_parent_id: z.string(),
  junjo_service_name: z.string(),
  junjo_span_type: z.nativeEnum(JunjoSpanType),
  junjo_initial_state: z.record(z.any()),
  junjo_final_state: z.record(z.any()),
})
export type OtelSpan = z.infer<typeof OtelSpanSchema>

export const WorkflowSpansE2EResponseSchema = z.object({
  workflowLineage: z.array(OtelSpanSchema),
  workflowSpans: z.array(OtelSpanSchema),
})
export type WorkflowSpansE2EResponse = z.infer<typeof WorkflowSpansE2EResponseSchema>
