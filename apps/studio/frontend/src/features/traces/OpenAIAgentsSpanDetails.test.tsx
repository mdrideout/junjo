import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import OpenAIAgentsSpanDetails from './OpenAIAgentsSpanDetails'
import type { OpenAIAgentsTelemetry } from './schemas/openai-agents-telemetry'

const basePayload = {
  source_class: 'agents.tracing.span_data.AgentSpanData',
  source_type: 'agent',
  trace_id: 'trace_example',
  span_id: 'span_agent',
  parent_span_id: 'span_task',
  started_at: '2026-08-23T12:00:00.100000+00:00',
  ended_at: '2026-08-23T12:00:00.900000+00:00',
  trace_metadata: null,
  tracing_api_key_configured: false,
  data: { name: 'Local place coordinator', tools: ['run_local_place_workflow'] },
  error: null,
}

describe('OpenAIAgentsSpanDetails', () => {
  it('shows structured identity, source data, and the raw payload', () => {
    const telemetry: OpenAIAgentsTelemetry = {
      kind: 'span',
      schemaVersion: 1,
      sourceType: 'agent',
      knownSourceType: true,
      payload: basePayload,
      rawPayload: basePayload,
    }

    render(<OpenAIAgentsSpanDetails telemetry={telemetry} />)

    expect(screen.getByRole('region', { name: 'OpenAI Agents SDK telemetry' })).toBeInTheDocument()
    expect(screen.getByText('Source trace ID')).toBeInTheDocument()
    expect(screen.getByText('Source span ID')).toBeInTheDocument()
    expect(screen.getByText('Agent data')).toBeInTheDocument()
    expect(screen.getByText('Raw payload')).toBeInTheDocument()
  })

  it('labels a future source type without discarding its payload', () => {
    const telemetry: OpenAIAgentsTelemetry = {
      kind: 'span',
      schemaVersion: 1,
      sourceType: 'future_operation',
      knownSourceType: false,
      payload: { ...basePayload, source_type: 'future_operation' },
      rawPayload: { ...basePayload, source_type: 'future_operation' },
    }

    render(<OpenAIAgentsSpanDetails telemetry={telemetry} />)

    expect(screen.getByText(/not recognized by this Studio version/)).toBeInTheDocument()
    expect(screen.getByText('future_operation data')).toBeInTheDocument()
    expect(screen.getByText('Raw payload')).toBeInTheDocument()
  })

  it('keeps malformed versioned telemetry visible', () => {
    render(
      <OpenAIAgentsSpanDetails
        telemetry={{
          kind: 'invalid',
          schemaVersion: 1,
          sourceType: 'agent',
          rawPayload: '{',
        }}
      />,
    )

    expect(screen.getByText(/could not parse/)).toBeInTheDocument()
    expect(screen.getByText('Raw payload')).toBeInTheDocument()
  })
})
