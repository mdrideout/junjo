import { configureStore } from '@reduxjs/toolkit'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import { workflowPath } from '../../../util/telemetry-paths'
import { OtelSpanSchema } from '../../traces/schemas/schemas'
import SpanFailuresList from './SpanFailuresList'
import workflowDetailSlice from './store/slice'

describe('SpanFailuresList', () => {
  it('keeps Workflow selection and the canonical child-span URL synchronized', async () => {
    const user = userEvent.setup()
    const spans = OtelSpanSchema.array().parse(
      structuredClone(loadJunjoTransportFixtureCase('failed_executable_with_error_type').spans),
    )
    const workflowSpan = spans.find((span) => span.span_id === '4444444444444441')
    const failedSpan = spans.find((span) => span.span_id === '4444444444444443')
    if (!workflowSpan || !failedSpan) throw new Error('Expected failed Workflow fixture spans')

    const store = configureStore({
      reducer: { workflowDetailState: workflowDetailSlice },
    })
    const initialPath = workflowPath(
      failedSpan.service_name,
      failedSpan.trace_id,
      workflowSpan.span_id,
    )
    const expectedPath = workflowPath(
      failedSpan.service_name,
      failedSpan.trace_id,
      workflowSpan.span_id,
      failedSpan.span_id,
    )
    const router = createMemoryRouter(
      [{
        path: '/workflows/:serviceName/:traceId/:workflowSpanId/:spanId?',
        element: <SpanFailuresList spans={[failedSpan]} />,
      }],
      { initialEntries: [initialPath] },
    )

    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    await user.click(screen.getByRole('button', { name: failedSpan.name }))

    await waitFor(() => expect(router.state.location.pathname).toBe(expectedPath))
    expect(store.getState().workflowDetailState.activeSpanIdentity).toEqual({
      traceId: failedSpan.trace_id,
      spanId: failedSpan.span_id,
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.openFailuresTrigger).toBe(1)
  })
})
