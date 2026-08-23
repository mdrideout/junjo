import { describe, expect, it } from 'vitest'
import type { OtelSpan } from '../../traces/schemas/schemas'
import { spanPresentation } from './span-presentation'

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

describe('spanPresentation', () => {
  it('separates standard GenAI kinds from their human names', () => {
    expect(spanPresentation(span({
      'gen_ai.operation.name': 'invoke_workflow',
      'gen_ai.workflow.name': 'Agent workflow',
    }))).toEqual({ kind: 'Workflow', name: 'Agent workflow' })
    expect(spanPresentation(span({
      'gen_ai.operation.name': 'invoke_agent',
      'gen_ai.agent.name': 'OpenAI coordinator',
    }))).toEqual({ kind: 'Agent', name: 'OpenAI coordinator' })
    expect(spanPresentation(span({
      'gen_ai.operation.name': 'execute_tool',
      'gen_ai.tool.name': 'run_local_place_workflow',
    }))).toEqual({ kind: 'Tool', name: 'run_local_place_workflow' })
    expect(spanPresentation(span({
      'gen_ai.operation.name': 'chat',
      'gen_ai.response.model': 'scripted-model',
    }))).toEqual({ kind: 'LLM', name: 'scripted-model' })
  })

  it('separates native Junjo Agent, Node, LLM, tool, and Workflow kinds from their names', () => {
    expect(spanPresentation(span({
      'junjo.span_type': 'agent',
      'junjo.agent.name': 'Local place specialist',
    }, 'raw agent span'))).toEqual({ kind: 'Agent', name: 'Local place specialist' })
    expect(spanPresentation(span({
      'junjo.span_type': 'node',
    }, 'CreateDateIdeaResponseNode'))).toEqual({
      kind: 'Node',
      name: 'CreateDateIdeaResponseNode',
    })
    expect(spanPresentation(span({
      'junjo.agent.operation_type': 'model_request',
      'junjo.agent.model.name': 'gpt-5',
    }, 'model request 1'))).toEqual({ kind: 'LLM', name: 'gpt-5' })
    expect(spanPresentation(span({
      'junjo.agent.operation_type': 'tool',
      'junjo.agent.tool.name': 'lookup',
    }, 'tool lookup'))).toEqual({ kind: 'Tool', name: 'lookup' })
    expect(spanPresentation(span({
      'junjo.span_type': 'workflow',
    }, 'Local place workflow'))).toEqual({ kind: 'Workflow', name: 'Local place workflow' })
    expect(spanPresentation(span({
      'junjo.span_type': 'subflow',
    }, 'Nested local place workflow'))).toEqual({
      kind: 'Workflow',
      name: 'Nested local place workflow',
    })
  })

  it('labels marker-proven OpenAI turn and generation spans', () => {
    expect(spanPresentation(span({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.span.type': 'turn',
    }, 'turn 1 Local place coordinator'))).toEqual({
      kind: 'Turn',
      name: '1 Local place coordinator',
    })
    expect(spanPresentation(span({
      'junjo.openai_agents.schema_version': 1,
      'junjo.openai_agents.span.type': 'generation',
      'gen_ai.operation.name': 'chat',
      'gen_ai.request.model': 'scripted-model',
    }))).toEqual({ kind: 'LLM', name: 'scripted-model' })
  })

  it('falls back to the received span name when standard attributes are absent', () => {
    expect(spanPresentation(span({}))).toEqual({ kind: null, name: 'raw-span-name' })
  })
})
