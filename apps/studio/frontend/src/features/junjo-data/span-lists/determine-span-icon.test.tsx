import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { OtelSpan } from '../../traces/schemas/schemas'
import { SpanIconConstructor } from './determine-span-icon'

function span(attributes: Record<string, unknown>): OtelSpan {
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
    name: 'standard GenAI span',
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

function renderIcon(attributes: Record<string, unknown>) {
  return render(<SpanIconConstructor span={span(attributes)} active={false} />)
}

describe('SpanIconConstructor', () => {
  it('uses a 24px OpenAI mark for every OpenAI Agent and tool span', () => {
    const { container } = render(
      <>
        <SpanIconConstructor
          span={span({
            'junjo.openai_agents.schema_version': 1,
            'gen_ai.operation.name': 'invoke_agent',
            'gen_ai.agent.name': 'Coordinator',
          })}
          active={false}
        />
        <SpanIconConstructor
          span={span({
            'junjo.openai_agents.schema_version': 1,
            'gen_ai.operation.name': 'invoke_agent',
            'gen_ai.agent.name': 'Specialist subagent',
          })}
          active={false}
        />
        <SpanIconConstructor
          span={span({
            'junjo.openai_agents.schema_version': 1,
            'gen_ai.operation.name': 'execute_tool',
            'gen_ai.tool.name': 'run_local_place_workflow',
          })}
          active={false}
        />
      </>,
    )

    const marks = container.querySelectorAll('[data-span-icon="openai-agents"]')
    expect(marks).toHaveLength(3)
    expect(marks[0]).toHaveClass('size-5', 'scale-[1.2]')
  })

  it.each([
    ['invoke_workflow', { 'gen_ai.workflow.name': 'Agent workflow' }],
    ['chat', { 'gen_ai.response.model': 'gpt-5' }],
  ])('does not use the OpenAI mark for the %s span', (operation, details) => {
    const { container } = renderIcon({
      'gen_ai.operation.name': operation,
      ...details,
    })

    expect(container.querySelector('[data-span-icon="openai-agents"]')).toBeNull()
  })

  it('keeps native Junjo identity ahead of external GenAI presentation', () => {
    const { container } = renderIcon({
      'junjo.span_type': 'node',
      'gen_ai.operation.name': 'invoke_agent',
    })

    expect(container.querySelector('[data-span-icon="openai-agents"]')).toBeNull()
  })

  it.each(['invoke_agent', 'execute_tool'])(
    'does not label an unrelated %s operation as OpenAI Agents SDK',
    (operation) => {
      const { container } = renderIcon({
        'gen_ai.operation.name': operation,
      })

      expect(container.querySelector('[data-span-icon="openai-agents"]')).toBeNull()
    },
  )
})
