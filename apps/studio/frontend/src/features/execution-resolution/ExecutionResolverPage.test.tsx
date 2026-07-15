import { act, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolveExecution } from './fetch/resolve-execution'
import ExecutionResolverPage from './ExecutionResolverPage'

vi.mock('./fetch/resolve-execution', () => ({ resolveExecution: vi.fn() }))
vi.mock('./ResolvedExecutionDetail', () => ({
  ResolvedExecutionDetail: () => <div>Workflow detail</div>,
}))

const resolverUrl = (
  '/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat'
  + '&executable_type=workflow&runtime_id=workflow-run&destination=detail'
)

function renderResolver() {
  const router = createMemoryRouter(
    [{ path: '/resolve/executable', element: <ExecutionResolverPage /> }],
    { initialEntries: [resolverUrl] },
  )
  render(<RouterProvider router={router} />)
  return router
}

const resolution = {
  service_namespace: 'junjo.examples',
  service_name: 'ai-chat',
  executable_type: 'workflow' as const,
  runtime_id: 'workflow-run',
  trace_id: '1'.repeat(32),
  span_id: 'a'.repeat(16),
  detail_path: `/workflows/ai-chat/${'1'.repeat(32)}/${'a'.repeat(16)}`,
  trace_path: `/traces/ai-chat/${'1'.repeat(32)}/${'a'.repeat(16)}`,
}

describe('ExecutionResolverPage', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('renders semantic execution content immediately while telemetry is arriving', async () => {
    vi.mocked(resolveExecution).mockResolvedValue(null)
    renderResolver()

    expect(await screen.findByRole('heading', { name: 'Workflow execution' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Telemetry is still arriving')
    expect(screen.queryByText(/attempt/i)).not.toBeInTheDocument()
  })

  it('renders resolved detail in place and keeps the semantic URL canonical', async () => {
    vi.mocked(resolveExecution).mockResolvedValue(resolution)
    const router = renderResolver()

    expect(await screen.findByText('Workflow detail')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/resolve/executable')
    expect(router.state.location.search).toContain('runtime_id=workflow-run')
  })

  it('continues polling beyond the former deadline with capped backoff', async () => {
    vi.useFakeTimers()
    vi.mocked(resolveExecution).mockResolvedValue(null)
    renderResolver()

    await act(async () => {})
    for (let retry = 0; retry < 18; retry += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000)
      })
    }

    expect(resolveExecution).toHaveBeenCalledTimes(19)
    expect(screen.getByRole('status')).toHaveTextContent('Telemetry is still arriving')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows real resolution failures instead of treating them as pending', async () => {
    vi.mocked(resolveExecution).mockRejectedValue(new Error('ambiguous execution identity'))
    renderResolver()

    expect(await screen.findByRole('alert')).toHaveTextContent('ambiguous execution identity')
  })
})
