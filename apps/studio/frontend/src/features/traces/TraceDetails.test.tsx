import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { createAppStore } from '../../root-store/store'
import type { OtelSpan } from './schemas/schemas'
import { TracesStateActions } from './store/slice'
import { makeTraceEvidence } from './testing/make-trace-evidence'
import TraceDetails from './TraceDetails'

function span(traceId: string, spanId: string, serviceName: string, name: string): OtelSpan {
  return {
    trace_id: traceId,
    span_id: spanId,
    parent_span_id: null,
    service_name: serviceName,
    name,
    kind: 'SERVER',
    start_time: '2026-06-21T20:00:00.000000+00:00',
    end_time: '2026-06-21T20:00:01.000000+00:00',
    status_code: '0',
    status_message: '',
    attributes_json: {},
    events_json: [],
    links_json: [],
    trace_flags: 0,
    trace_state: null,
    dropped_attributes_count: 0,
    dropped_events_count: 0,
    dropped_links_count: 0,
    resource_attributes_json: { 'service.name': serviceName },
    resource_dropped_attributes_count: 0,
  }
}

function storeWithEvidence(...traceSpans: OtelSpan[][]) {
  const store = createAppStore()
  for (const spans of traceSpans) {
    store.dispatch(TracesStateActions.traceEvidenceRequestSucceeded({
      traceId: spans[0].trace_id,
      data: makeTraceEvidence(spans),
    }))
  }
  return store
}

describe('TraceDetails navigation', () => {
  it('uses the URL span identity when navigating between traces', async () => {
    const traceA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    const traceB = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    const spanA = span(traceA, '1111111111111111', 'service-a', 'trace-a-span')
    const spanB = span(traceB, '2222222222222222', 'service-b', 'trace-b-span')
    const store = storeWithEvidence([spanA], [spanB])
    const traceBPath = `/traces/service-b/${traceB}`
    const router = createMemoryRouter(
      [{ path: '/traces/:serviceName/:traceId/:spanId?', element: <TraceDetails /> }],
      { initialEntries: [`/traces/service-a/${traceA}/${spanA.span_id}`] },
    )

    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    await screen.findByText('Basic Information')
    await act(async () => {
      await router.navigate(traceBPath)
    })

    await waitFor(() => expect(router.state.location.pathname).toBe(traceBPath))
    expect(screen.getByText('No span selected')).toBeInTheDocument()
    expect(screen.queryByText('trace-a-span')).not.toBeInTheDocument()
  })

  it('keeps resolver-embedded span selection local to its semantic route', async () => {
    const user = userEvent.setup()
    const traceId = 'cccccccccccccccccccccccccccccccc'
    const rootSpan = span(traceId, '3333333333333333', 'service-c', 'resolver-root')
    const childSpan = {
      ...span(traceId, '4444444444444444', 'service-c', 'resolver-child'),
      parent_span_id: rootSpan.span_id,
    }
    const store = storeWithEvidence([rootSpan, childSpan])
    const router = createMemoryRouter(
      [{
        path: '/resolve/executable',
        element: (
          <TraceDetails
            routeIdentity={{
              serviceName: 'service-c',
              traceId,
              spanId: rootSpan.span_id,
            }}
          />
        ),
      }],
      { initialEntries: ['/resolve/executable'] },
    )

    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    await user.click(screen.getByText('resolver-child'))

    expect(router.state.location.pathname).toBe('/resolve/executable')
    expect(screen.getAllByText('resolver-child')).toHaveLength(2)
  })
})
