import { z } from 'zod'

export enum JunjoSpanType {
  WORKFLOW = 'workflow',
  SUBFLOW = 'subflow',
  NODE = 'node',
  NODE_GATHER = 'node_gather',
  OTHER = '',
}

export enum NodeEventType {
  SET_STATE = 'set_state',
}

export const OtelSpanSchema = z.object({
  span_id: z.string(),
  trace_id: z.string(),
  service_name: z.string(),
  attributes_json: z.record(z.any()),
  start_time: z.string().datetime({ offset: true }),
  end_time: z.string().datetime({ offset: true }),
  events_json: z.array(z.record(z.any())),
  kind: z.string(),
  links_json: z.array(z.record(z.any())),
  name: z.string(),
  parent_span_id: z.string().nullable(),
  status_code: z.string(),
  status_message: z.string(),
  trace_flags: z.number(),
  trace_state: z.any(),
  junjo_id: z.string(),
  junjo_parent_id: z.string(),
  junjo_span_type: z.nativeEnum(JunjoSpanType),
  junjo_wf_state_start: z.record(z.any()),
  junjo_wf_state_end: z.record(z.any()),
  junjo_wf_graph_structure: z.record(z.any()),
})
export type OtelSpan = z.infer<typeof OtelSpanSchema>

export const WorkflowSpansE2EResponseSchema = z.object({
  workflowLineage: z.array(OtelSpanSchema),
  workflowSpans: z.array(OtelSpanSchema),
})
export type WorkflowSpansE2EResponse = z.infer<typeof WorkflowSpansE2EResponseSchema>

// Define the schema for the known event type
export const NodeSetStateAttributesSchema = z.object({
  id: z.string(),
  'junjo.state_json_patch': z.string(), // Assuming this is a JSON string
  'junjo.store.action': z.string(),
  'junjo.store.name': z.string(),
})

export const NodeSetStateEventSchema = z.object({
  name: z.literal('set_state'), // Discriminator field
  timeUnixNano: z.number(),
  attributes: NodeSetStateAttributesSchema,
})
export type NodeSetStateEvent = z.infer<typeof NodeSetStateEventSchema>
