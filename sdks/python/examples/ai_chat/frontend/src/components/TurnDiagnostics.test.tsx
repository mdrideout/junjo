import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { PublicConfig, Turn } from '../api/schemas'
import { TurnDiagnostics } from './TurnDiagnostics'

const turn: Turn = {
  object_type: 'ai_chat.turn',
  schema_version: 1,
  id: 'turn-1',
  revision: 3,
  conversation_id: 'conversation-1',
  sequence: 1,
  status: 'completed',
  context_policy: { id: 'recent-completed-turns', version: 1, recent_turn_limit: 8 },
  user_message: {
    id: 'user-1', turn_id: 'turn-1', role: 'user', content: 'Hello',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:00.000Z',
  },
  assistant_message: {
    id: 'assistant-1', turn_id: 'turn-1', role: 'assistant', content: 'Hi',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:01.000Z',
  },
  execution_references: { workflow_run_id: 'workflow-run', agent_run_id: 'agent-run' },
  failure: null,
  created_at: '2026-07-14T12:00:00.000Z',
  updated_at: '2026-07-14T12:00:02.000Z',
  completed_at: '2026-07-14T12:00:02.000Z',
}

const studioConfig: PublicConfig = {
  studio_frontend_base_url: 'http://localhost:26151',
  service_namespace: 'junjo.examples',
  service_name: 'ai-chat',
}

afterEach(cleanup)

describe('TurnDiagnostics', () => {
  it('links durable runtime references through the Studio resolver contract', () => {
    render(<TurnDiagnostics turn={turn} config={studioConfig} />)

    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(3)
    expect(links[0]).toHaveAttribute(
      'href',
      'http://localhost:26151/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=workflow&runtime_id=workflow-run&destination=detail',
    )
    expect(links[1]).toHaveAttribute(
      'href',
      'http://localhost:26151/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=agent&runtime_id=agent-run&destination=detail',
    )
    expect(links[2]).toHaveAttribute('href', expect.stringContaining('destination=trace'))
  })

  it('shows references without links when no Studio frontend is configured', () => {
    render(<TurnDiagnostics
      turn={turn}
      config={{ ...studioConfig, studio_frontend_base_url: null }}
    />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('workflow-run')).toBeInTheDocument()
    expect(screen.getByText('agent-run')).toBeInTheDocument()
  })

  it('expands terminal failure evidence', () => {
    const failedTurn: Turn = {
      ...turn,
      status: 'failed',
      assistant_message: null,
      failure: {
        code: 'agent_execution_failed',
        detail: 'Agent execution failed.',
        termination_reason: 'tool_input_validation_error',
      },
    }

    render(<TurnDiagnostics turn={failedTurn} config={studioConfig} />)

    expect(screen.getByText('Turn diagnostics').closest('details')).toHaveAttribute('open')
    expect(screen.getByText('agent_execution_failed')).toBeInTheDocument()
    expect(screen.getByText('Agent execution failed.')).toBeInTheDocument()
    expect(screen.getByText('tool_input_validation_error')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open failures in Studio' })).toHaveAttribute(
      'href',
      'http://localhost:26151/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=workflow&runtime_id=workflow-run&destination=failures',
    )
  })
})
