import { describe, expect, it } from 'vitest'
import type { OtelSpan } from '../../traces/schemas/schemas'
import { spanNameConstructor } from './span-name-constructor'

function span(attributes: Record<string, unknown>, name = 'raw-span-name'): OtelSpan {
  return {
    span_id: 'a'.repeat(16),
    trace_id: '1'.repeat(32),
    service_name: 'base-openai-agents',
    attributes_json: attributes,
    start_time: '2026-08-18T12:00:00Z',
    end_time: '2026-08-18T12:00:01Z',
    events_json: [],
    kind: 'INTERNAL',
    links_json: [],
    name,
    parent_span_id: null,
    status_code: 'OK',
    status_message: '',
    trace_flags: 1,
    trace_state: null,
    dropped_attributes_count: 0,
    dropped_events_count: 0,
    dropped_links_count: 0,
    resource_attributes_json: { 'service.name': 'base-openai-agents' },
    resource_dropped_attributes_count: 0,
  }
}

describe('spanNameConstructor', () => {
  it('labels standard OpenTelemetry GenAI Agent, tool, and model operations', () => {
    expect(spanNameConstructor(span({
      'gen_ai.operation.name': 'invoke_agent',
      'gen_ai.agent.name': 'OpenAI coordinator',
    }))).toBe('Agent — OpenAI coordinator')
    expect(spanNameConstructor(span({
      'gen_ai.operation.name': 'execute_tool',
      'gen_ai.tool.name': 'run_local_place_workflow',
    }))).toBe('Tool call — run_local_place_workflow')
    expect(spanNameConstructor(span({
      'gen_ai.operation.name': 'chat',
      'gen_ai.response.model': 'scripted-model',
    }))).toBe('Model call — scripted-model')
  })

  it('falls back to the received span name when standard attributes are absent', () => {
    expect(spanNameConstructor(span({}))).toBe('raw-span-name')
  })
})
