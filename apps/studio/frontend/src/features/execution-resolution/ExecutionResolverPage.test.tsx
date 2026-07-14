import { act, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resolveExecution } from './fetch/resolve-execution'
import ExecutionResolverPage from './ExecutionResolverPage'

vi.mock('./fetch/resolve-execution', () => ({ resolveExecution: vi.fn() }))

const resolverUrl = (
  '/resolve/executable?service_namespace=junjo.examples&service_name=ai-chat'
  + '&executable_type=workflow&runtime_id=workflow-run&destination=detail'
)

function renderResolver() {
  const router = createMemoryRouter(
    [
      { path: '/resolve/executable', element: <ExecutionResolverPage /> },
      { path: '/workflows/:serviceName/:traceId/:spanId', element: <div>Workflow detail</div> },
    ],
    { initialEntries: [resolverUrl] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('ExecutionResolverPage', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('replaces the stable resolver URL with the exact semantic detail route', async () => {
    vi.mocked(resolveExecution).mockResolvedValue({
      service_namespace: 'junjo.examples',
      service_name: 'ai-chat',
      executable_type: 'workflow',
      runtime_id: 'workflow-run',
      trace_id: '1'.repeat(32),
      span_id: 'a'.repeat(16),
      detail_path: `/workflows/ai-chat/${'1'.repeat(32)}/${'a'.repeat(16)}`,
      trace_path: `/traces/ai-chat/${'1'.repeat(32)}/${'a'.repeat(16)}`,
    })
    const router = renderResolver()

    expect(await screen.findByText('Workflow detail')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(
      `/workflows/ai-chat/${'1'.repeat(32)}/${'a'.repeat(16)}`,
    )
  })

  it('stops polling after the bounded ingestion window', async () => {
    vi.useFakeTimers()
    vi.mocked(resolveExecution).mockResolvedValue(null)
    renderResolver()

    await act(async () => {})
    for (let retry = 1; retry < 15; retry += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000)
      })
    }

    expect(resolveExecution).toHaveBeenCalledTimes(15)
    expect(screen.getByRole('alert')).toHaveTextContent('resolution window ended')
  })
})
