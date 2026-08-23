import { z } from 'zod'

export const OPENAI_AGENTS_SCHEMA_VERSION_ATTRIBUTE = 'junjo.openai_agents.schema_version'
export const OPENAI_AGENTS_SPAN_TYPE_ATTRIBUTE = 'junjo.openai_agents.span.type'
export const OPENAI_AGENTS_SPAN_DATA_ATTRIBUTE = 'junjo.openai_agents.span.data'
export const OPENAI_AGENTS_TRACE_DATA_ATTRIBUTE = 'junjo.openai_agents.trace.data'

export const OPENAI_AGENTS_KNOWN_SPAN_TYPES = [
  'agent',
  'custom',
  'function',
  'generation',
  'guardrail',
  'handoff',
  'mcp_tools',
  'response',
  'speech',
  'speech_group',
  'task',
  'transcription',
  'turn',
] as const

const OpenAIAgentsErrorSchema = z
  .object({
    message: z.string(),
    data: z.record(z.unknown()).nullable(),
  })
  .strict()
  .nullable()

const OpenAIAgentsTracePayloadSchema = z
  .object({
    source_class: z.string().min(1),
    trace_id: z.string().min(1),
    name: z.string().min(1),
    group_id: z.string().nullable(),
    metadata: z.record(z.unknown()).nullable(),
    started_at: z.string().datetime({ offset: true }),
    ended_at: z.string().datetime({ offset: true }),
    tracing_api_key_configured: z.boolean(),
  })
  .strict()

const OpenAIAgentsSpanPayloadSchema = z
  .object({
    source_class: z.string().min(1),
    source_type: z.string().min(1),
    trace_id: z.string().min(1),
    span_id: z.string().min(1),
    parent_span_id: z.string().nullable(),
    started_at: z.string().datetime({ offset: true }).nullable(),
    ended_at: z.string().datetime({ offset: true }).nullable(),
    trace_metadata: z.record(z.unknown()).nullable(),
    tracing_api_key_configured: z.boolean(),
    data: z.unknown(),
    error: OpenAIAgentsErrorSchema,
  })
  .strict()

export type OpenAIAgentsTracePayload = z.infer<typeof OpenAIAgentsTracePayloadSchema>
export type OpenAIAgentsSpanPayload = z.infer<typeof OpenAIAgentsSpanPayloadSchema>

export type OpenAIAgentsTelemetry =
  | {
      kind: 'trace'
      schemaVersion: 1
      payload: OpenAIAgentsTracePayload
      rawPayload: unknown
    }
  | {
      kind: 'span'
      schemaVersion: 1
      sourceType: string
      knownSourceType: boolean
      payload: OpenAIAgentsSpanPayload
      rawPayload: unknown
    }
  | {
      kind: 'invalid'
      schemaVersion: 1
      sourceType: string | null
      rawPayload: unknown
    }

export function parseOpenAIAgentsTelemetry(
  attributes: Record<string, unknown>,
): OpenAIAgentsTelemetry | null {
  if (attributes[OPENAI_AGENTS_SCHEMA_VERSION_ATTRIBUTE] !== 1) {
    return null
  }

  const sourceTypeAttribute = attributes[OPENAI_AGENTS_SPAN_TYPE_ATTRIBUTE]
  const sourceType = typeof sourceTypeAttribute === 'string' ? sourceTypeAttribute : null
  const spanPayload = parseJsonAttribute(attributes[OPENAI_AGENTS_SPAN_DATA_ATTRIBUTE])
  if (spanPayload.present) {
    const parsed = OpenAIAgentsSpanPayloadSchema.safeParse(spanPayload.value)
    if (!parsed.success || sourceType === null || parsed.data.source_type !== sourceType) {
      return {
        kind: 'invalid',
        schemaVersion: 1,
        sourceType,
        rawPayload: spanPayload.value,
      }
    }
    return {
      kind: 'span',
      schemaVersion: 1,
      sourceType,
      knownSourceType: OPENAI_AGENTS_KNOWN_SPAN_TYPES.includes(
        sourceType as (typeof OPENAI_AGENTS_KNOWN_SPAN_TYPES)[number],
      ),
      payload: parsed.data,
      rawPayload: spanPayload.value,
    }
  }

  const tracePayload = parseJsonAttribute(attributes[OPENAI_AGENTS_TRACE_DATA_ATTRIBUTE])
  if (tracePayload.present) {
    const parsed = OpenAIAgentsTracePayloadSchema.safeParse(tracePayload.value)
    if (parsed.success) {
      return {
        kind: 'trace',
        schemaVersion: 1,
        payload: parsed.data,
        rawPayload: tracePayload.value,
      }
    }
    return {
      kind: 'invalid',
      schemaVersion: 1,
      sourceType,
      rawPayload: tracePayload.value,
    }
  }

  return {
    kind: 'invalid',
    schemaVersion: 1,
    sourceType,
    rawPayload: null,
  }
}

function parseJsonAttribute(value: unknown):
  | { present: false; value: null }
  | { present: true; value: unknown } {
  if (value === undefined) {
    return { present: false, value: null }
  }
  if (typeof value !== 'string') {
    return { present: true, value }
  }
  try {
    return { present: true, value: JSON.parse(value) as unknown }
  } catch {
    return { present: true, value }
  }
}
