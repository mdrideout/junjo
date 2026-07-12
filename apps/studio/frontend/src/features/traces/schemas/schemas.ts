import { z } from 'zod'

export enum JunjoSpanType {
  WORKFLOW = 'workflow',
  SUBFLOW = 'subflow',
  NODE = 'node',
  RUN_CONCURRENT = 'run_concurrent',
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
  // Note: Junjo attributes (junjo.*, junjo.workflow.*) are in attributes_json.
  // Use SpanAccessor from utils/span-accessor.ts for typed access.
})
export type OtelSpan = z.infer<typeof OtelSpanSchema>

export const WorkflowSpansE2EResponseSchema = z.object({
  workflowLineage: z.array(OtelSpanSchema),
  workflowSpans: z.array(OtelSpanSchema),
})
export type WorkflowSpansE2EResponse = z.infer<typeof WorkflowSpansE2EResponseSchema>

const SpanEventAttributesSchema = z.record(z.unknown())

export const OtelSpanEventSchema = z.object({
  name: z.string(),
  timeUnixNano: z.number(),
  attributes: SpanEventAttributesSchema,
})
export type OtelSpanEvent = z.infer<typeof OtelSpanEventSchema>

// Define the schema for events_json set_state events
export const NodeSetStateAttributesSchema = z.object({
  id: z.string(),
  'junjo.state_json_patch': z.string(), // Assuming this is a JSON string
  'junjo.store.action': z.string(),
  'junjo.store.name': z.string(),
  'junjo.store.id': z.string(),
})

export const JunjoSetStateEventSchema = OtelSpanEventSchema.extend({
  name: z.literal('set_state'),
  attributes: NodeSetStateAttributesSchema,
})
export type JunjoSetStateEvent = z.infer<typeof JunjoSetStateEventSchema>

export const NodeExceptionAttributesSchema = z.object({
  'exception.message': z.string().optional(),
  'exception.stacktrace': z.string().optional(),
  'exception.type': z.string(),
  'exception.escaped': z.union([z.string(), z.boolean()]).optional(),
})

export const JunjoExceptionEventSchema = OtelSpanEventSchema.extend({
  name: z.literal('exception'),
  attributes: NodeExceptionAttributesSchema,
})
export type JunjoExceptionEvent = z.infer<typeof JunjoExceptionEventSchema>

export const JunjoHookErrorAttributesSchema = z.object({
  'junjo.hook.event': z.string(),
  'junjo.hook.callback': z.string(),
  'junjo.hook.error.type': z.string(),
  'junjo.hook.error.message': z.string(),
  'exception.type': z.string(),
  'exception.message': z.string().optional(),
  'exception.stacktrace': z.string().optional(),
})

export const JunjoHookErrorEventSchema = OtelSpanEventSchema.extend({
  name: z.literal('junjo.hook_error'),
  attributes: JunjoHookErrorAttributesSchema,
})
export type JunjoHookErrorEvent = z.infer<typeof JunjoHookErrorEventSchema>
