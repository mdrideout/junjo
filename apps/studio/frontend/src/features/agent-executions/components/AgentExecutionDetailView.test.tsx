import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { makeAgentExecutionDetailFixture } from '../testing/fixtures'
import { AgentExecutionDetailView } from './AgentExecutionDetailView'

function renderDetail(detail = makeAgentExecutionDetailFixture()) {
  return render(
    <MemoryRouter>
      <AgentExecutionDetailView detail={detail} />
    </MemoryRouter>,
  )
}

describe('AgentExecutionDetailView', () => {
  it('renders a sequence-authoritative operation rail without inventing Tool operations', async () => {
    const detail = makeAgentExecutionDetailFixture()
    detail.operations.reverse()
    renderDetail(detail)

    const user = userEvent.setup()
    const rail = screen.getByRole('region', { name: 'Realized Agent operations' })
    const operationButtons = within(rail).getAllByRole('button')

    expect(operationButtons).toHaveLength(2)
    expect(within(operationButtons[0]!).getByText('1. Model', { exact: true })).toBeVisible()
    expect(within(operationButtons[1]!).getByText('2. Tool', { exact: true })).toBeVisible()

    expect(within(rail).getAllByText('delete_everything').length).toBeGreaterThanOrEqual(1)
    expect(within(rail).getByText('not admitted')).toBeInTheDocument()
    expect(within(rail).getByText('No Tool operation began for this request.')).toBeInTheDocument()

    await user.click(operationButtons[1]!)
    expect(within(rail).getByText('Requested arguments')).toBeInTheDocument()
    expect(within(rail).getByText('Returned candidate')).toBeInTheDocument()
    expect(within(rail).getByText('Validated result')).toBeInTheDocument()
  })

  it('keeps producer policy, candidate availability, and partial integrity distinct', () => {
    const detail = makeAgentExecutionDetailFixture()
    detail.input = {
      mode: 'redacted',
      policy: 'redacted',
      value: { message: '[REDACTED]' },
      reference: null,
      reason: null,
    }
    detail.output = {
      mode: 'excluded',
      policy: 'excluded',
      value: null,
      reference: null,
      reason: null,
    }
    detail.definition = {
      mode: 'reference',
      policy: 'reference',
      value: null,
      reference: 'opaque://agent-definition',
      reason: null,
    }
    const modelOperation = detail.operations[0]
    if (modelOperation?.operation_type !== 'model_request') throw new Error('Fixture model operation missing')
    modelOperation.request = {
      mode: 'missing',
      policy: null,
      value: null,
      reference: null,
      reason: 'The model request event was dropped.',
    }
    modelOperation.response_candidate = {
      available: false,
      payload: null,
      unavailable_reason: 'service_failed',
    }
    detail.integrity = {
      status: 'partial',
      diagnostics: [
        {
          code: 'missing_model_request',
          path: 'operations[0].request',
          message: 'The request payload is unavailable.',
        },
      ],
      loss_counts: {
        ...detail.integrity.loss_counts,
        span_dropped_events: 1,
      },
    }

    renderDetail(detail)

    expect(screen.getByText('Contract evidence: partial')).toBeInTheDocument()
    expect(screen.getAllByText('missing_model_request').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('span dropped events')).toBeInTheDocument()
    expect(screen.getByText('The model request event was dropped.')).toBeInTheDocument()
    expect(screen.getByText(/Candidate unavailable:/)).toHaveTextContent(
      'service_failed',
    )
    expect(screen.getByText('The declared telemetry policy intentionally excluded this payload.')).toBeInTheDocument()
    expect(screen.getAllByText('opaque://agent-definition').length).toBeGreaterThanOrEqual(1)
  })

  it('navigates backend-verified Store projections and links to nested and raw diagnostics', async () => {
    const detail = makeAgentExecutionDetailFixture()
    detail.nested_executables.push({
      executable_type: 'agent',
      parent_operation_sequence: 2,
      parent_operation_span_id: 'cccccccccccccccc',
      trace_id: detail.summary.trace_id,
      span_id: 'ffffffffffffffff',
      service: detail.summary.service,
      definition_id: 'agent_definition_sha256:nested-fixture',
      runtime_id: 'agent_run_01JNESTED',
      structural_id: `agent_sha256:${'b'.repeat(64)}`,
      name: 'Nested Reviewer',
    })
    renderDetail(detail)
    const user = userEvent.setup()

    expect(screen.getByText('Backend replay verified')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open parent diagnostics' })).toHaveAttribute(
      'href',
      '/traces/ai-chat/11111111111111111111111111111111/eeeeeeeeeeeeeeee',
    )
    await user.click(screen.getByRole('button', { name: /2\. Tool/ }))
    expect(screen.getByText('Child executables invoked by this Tool')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /1\. remember_name/ }))
    expect(screen.getByText('Before')).toBeInTheDocument()
    expect(screen.getByText('After')).toBeInTheDocument()
    expect(screen.getByText('Emitted RFC 6902 patch')).toBeInTheDocument()

    expect(screen.getByRole('link', { name: 'Raw trace' })).toHaveAttribute(
      'href',
      '/traces/ai-chat/11111111111111111111111111111111/aaaaaaaaaaaaaaaa',
    )
    const nestedLinks = screen.getAllByRole('link', { name: 'Open diagnostics' })
    expect(nestedLinks[0]).toHaveAttribute(
      'href',
      '/workflows/ai-chat/11111111111111111111111111111111/dddddddddddddddd',
    )
    expect(nestedLinks[1]).toHaveAttribute(
      'href',
      '/agents/11111111111111111111111111111111/ffffffffffffffff',
    )
  })

  it.each(['workflow', 'subflow'] as const)(
    'links a %s semantic parent to Workflow diagnostics',
    (executableType) => {
      const detail = makeAgentExecutionDetailFixture()
      if (detail.parent_executable === null) throw new Error('Fixture parent missing')
      detail.parent_executable.executable_type = executableType

      renderDetail(detail)

      expect(screen.getByRole('link', { name: 'Open parent diagnostics' })).toHaveAttribute(
        'href',
        '/workflows/ai-chat/11111111111111111111111111111111/eeeeeeeeeeeeeeee',
      )
    },
  )

  it('does not replay Store patches in the browser when backend verification failed', async () => {
    const detail = makeAgentExecutionDetailFixture()
    detail.state.reconstructable = false
    detail.state.reconstruction_status = 'failed'
    detail.state.reconstruction_reason = 'patch_replay_mismatch'
    detail.state.transitions[0]!.before = null
    detail.state.transitions[0]!.after = null
    renderDetail(detail)

    const user = userEvent.setup()
    expect(screen.getByText('Replay verification failed')).toBeInTheDocument()
    expect(screen.getAllByText('patch_replay_mismatch').length).toBeGreaterThanOrEqual(1)

    await user.click(screen.getByRole('button', { name: /1\. remember_name/ }))
    expect(screen.getAllByText('Backend replay did not produce this projection.')).toHaveLength(2)
  })
})
