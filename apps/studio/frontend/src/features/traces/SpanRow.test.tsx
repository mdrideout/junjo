import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider, useNavigate } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { tracesPath, workflowPath } from '../../util/telemetry-paths'
import type { OtelSpan } from './schemas/schemas'
import SpanRow from './SpanRow'

function workflowSpan(): OtelSpan {
  return {
    trace_id: '11111111111111111111111111111111',
    span_id: '2222222222222222',
    parent_span_id: null,
    service_name: 'test-service',
    name: 'Test Workflow',
    kind: 'SERVER',
    start_time: '2026-06-21T20:00:00.000000+00:00',
    end_time: '2026-06-21T20:00:01.000000+00:00',
    status_code: '0',
    status_message: '',
    attributes_json: { 'junjo.span_type': 'workflow' },
    events_json: [],
    links_json: [],
    trace_flags: 0,
    trace_state: null,
    dropped_attributes_count: 0,
    dropped_events_count: 0,
    dropped_links_count: 0,
    resource_attributes_json: { 'service.name': 'test-service' },
    resource_dropped_attributes_count: 0,
  }
}

describe('SpanRow', () => {
  it('lets the nested Workflow Explorer link own its navigation', async () => {
    const user = userEvent.setup()
    const span = workflowSpan()
    const selectSpan = vi.fn()
    const openFailures = vi.fn()

    function RowWithTraceSelection() {
      const navigate = useNavigate()
      return (
        <SpanRow
          span={span}
          isActiveSpan={false}
          onClick={(selectedSpan) => {
            selectSpan(selectedSpan)
            navigate(tracesPath(
              selectedSpan.service_name,
              selectedSpan.trace_id,
              selectedSpan.span_id,
            ))
          }}
          onOpenFailures={openFailures}
        />
      )
    }

    const router = createMemoryRouter(
      [{ path: '*', element: <RowWithTraceSelection /> }],
      { initialEntries: [tracesPath(span.service_name, span.trace_id)] },
    )
    render(<RouterProvider router={router} />)

    const link = screen.getByRole('link', { name: /Workflow Explorer/ })
    const destination = workflowPath(
      span.service_name,
      span.trace_id,
      span.span_id,
      span.span_id,
    )
    expect(link).toHaveAttribute('href', destination)

    await user.click(link)

    expect(selectSpan).not.toHaveBeenCalled()
    expect(router.state.location.pathname).toBe(destination)
  })

  it('gives a failure chip its own selection intent', async () => {
    const user = userEvent.setup()
    const failedSpan = {
      ...workflowSpan(),
      attributes_json: {
        'error.type': 'ValueError',
      },
    }
    const selectSpan = vi.fn()
    const openFailures = vi.fn()

    render(
      <SpanRow
        span={failedSpan}
        isActiveSpan={false}
        onClick={selectSpan}
        onOpenFailures={openFailures}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'failures' }))

    expect(openFailures).toHaveBeenCalledWith(failedSpan)
    expect(selectSpan).not.toHaveBeenCalled()
  })
})
