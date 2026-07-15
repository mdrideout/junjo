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

const debugConfig: PublicConfig = {
  debug_enabled: true,
  studio_ui_url: 'http://localhost:26153',
  service_namespace: 'junjo.examples',
  service_name: 'ai-chat',
}

afterEach(cleanup)

describe('TurnDiagnostics', () => {
  it('links durable runtime references through the Studio resolver contract', () => {
    render(<TurnDiagnostics turn={turn} config={debugConfig} />)

    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(3)
    expect(links[0]).toHaveAttribute(
      'href',
      'http://localhost:26153/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=workflow&runtime_id=workflow-run&destination=detail',
    )
    expect(links[1]).toHaveAttribute(
      'href',
      'http://localhost:26153/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat&executable_type=agent&runtime_id=agent-run&destination=detail',
    )
    expect(links[2]).toHaveAttribute('href', expect.stringContaining('destination=trace'))
  })

  it('shows references without links when debug presentation is disabled', () => {
    render(<TurnDiagnostics turn={turn} config={{ ...debugConfig, debug_enabled: false }} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('workflow-run')).toBeInTheDocument()
    expect(screen.getByText('agent-run')).toBeInTheDocument()
  })
})
