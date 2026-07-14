import { configureStore } from '@reduxjs/toolkit'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { createMemoryRouter, Link, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import {
  JunjoSetStateEventSchema,
  OtelSpanSchema,
  type OtelSpan,
} from '../../traces/schemas/schemas'
import tracesSlice from '../../traces/store/slice'
import { rawStateEventIdentity } from './state-event-identity'
import WorkflowDetailPage from './WorkflowDetailPage'
import workflowDetailSlice, { WorkflowDetailStateActions } from './store/slice'

vi.mock('./WorkflowDetailNavButtons', () => ({ default: () => null }))
vi.mock('./WorkflowDetailStateDiff', () => ({ default: () => null }))
vi.mock('./WorkflowDetailStateNav', () => ({ default: () => null }))
vi.mock('../span-lists/TabbedSpanLists', () => ({ default: () => null }))
vi.mock('../../../mermaidjs/RenderJunjoGraphList', () => ({ default: () => null }))
vi.mock('../../../components/forms/switch', () => ({ Switch: () => null }))
vi.mock('./use-active-workflow-store-diagnostic', () => ({
  useActiveWorkflowStoreDiagnostic: () => ({
    ownerSpan: undefined,
    request: { data: null, loading: false, error: null },
  }),
}))

function loadSpans(caseName: string): OtelSpan[] {
  return OtelSpanSchema.array().parse(
    structuredClone(loadJunjoTransportFixtureCase(caseName).spans),
  )
}

function findSpan(spans: OtelSpan[], spanId: string): OtelSpan {
  const span = spans.find((candidate) => candidate.span_id === spanId)
  if (span === undefined) throw new Error(`Span ${spanId} missing`)
  return span
}

function stateEventSelection(spans: OtelSpan[], eventId: string) {
  for (const span of spans) {
    for (const event of span.events_json) {
      const parsed = JunjoSetStateEventSchema.safeParse(event)
      if (parsed.success && parsed.data.attributes.id === eventId) {
        const identity = rawStateEventIdentity(span.span_id, parsed.data)
        return { identity, selection: { ...identity, event: parsed.data } }
      }
    }
  }
  throw new Error(`State event ${eventId} missing`)
}

function makeStore(basicSpans: OtelSpan[], subflowSpans: OtelSpan[]) {
  const staleSpan = findSpan(basicSpans, '1111111111111113')
  const staleEvent = stateEventSelection(basicSpans, 'state-event-basic-02')
  const basicTraceId = basicSpans[0].trace_id
  const subflowTraceId = subflowSpans[0].trace_id

  return configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
      tracesState: tracesSlice,
    },
    preloadedState: {
      workflowDetailState: {
        activeSpan: staleSpan,
        activeStateEvent: staleEvent.selection,
        stateEventScrollTarget: staleEvent.identity,
        openFailuresTrigger: 1,
      },
      tracesState: {
        serviceNames: { data: [], loading: false, error: false },
        traceSpans: {
          [basicTraceId]: basicSpans,
          [subflowTraceId]: subflowSpans,
        },
        loading: false,
        error: false,
      },
    },
  })
}

describe('WorkflowDetailPage route lifecycle', () => {
  it('replaces stale selection across Agent and direct Workflow links without resetting ordinary row selection', async () => {
    const user = userEvent.setup()
    const basicSpans = loadSpans('basic_workflow_success')
    const subflowSpans = loadSpans('subflow_with_parent_store')
    const basicWorkflow = findSpan(basicSpans, '1111111111111111')
    const subflowWorkflow = findSpan(subflowSpans, '2222222222222221')
    const subflowEventSpan = findSpan(subflowSpans, '2222222222222224')
    const differentSubflowSpan = findSpan(subflowSpans, '2222222222222222')
    const subflowEvent = stateEventSelection(subflowSpans, 'state-event-subflow-01')
    const nestedWorkflowRoute = `/workflows/subflow-service/${subflowWorkflow.trace_id}/${subflowWorkflow.span_id}`
    const basicWorkflowRoute = `/workflows/basic-service/${basicWorkflow.trace_id}/${basicWorkflow.span_id}`

    const store = makeStore(basicSpans, subflowSpans)
    const router = createMemoryRouter(
      [
        {
          path: '/agents/:traceId/:agentSpanId',
          element: <Link to={nestedWorkflowRoute}>Open nested Workflow</Link>,
        },
        {
          path: '/workflows/:serviceName/:traceId/:workflowSpanId/:spanId?',
          element: <WorkflowDetailPage />,
        },
      ],
      { initialEntries: ['/agents/agent-trace/agent-span'] },
    )

    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    await user.click(screen.getByRole('link', { name: 'Open nested Workflow' }))
    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpan?.span_id)
        .toBe(subflowWorkflow.span_id)
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.stateEventScrollTarget).toBeNull()
    expect(store.getState().workflowDetailState.openFailuresTrigger).toBeNull()

    act(() => {
      store.dispatch(WorkflowDetailStateActions.setActiveSpan(subflowEventSpan))
      store.dispatch(WorkflowDetailStateActions.setActiveStateEvent(subflowEvent.selection))
      store.dispatch(WorkflowDetailStateActions.setStateEventScrollTarget(subflowEvent.identity))
    })
    await act(async () => {
      await router.navigate(`${nestedWorkflowRoute}/${subflowEventSpan.span_id}`)
    })
    expect(store.getState().workflowDetailState.activeSpan?.span_id)
      .toBe(subflowEventSpan.span_id)
    expect(store.getState().workflowDetailState.activeStateEvent?.eventId)
      .toBe('state-event-subflow-01')

    await act(async () => {
      await router.navigate(`${nestedWorkflowRoute}/ffffffffffffffff`)
    })
    expect(await screen.findByRole('heading', { name: 'Span not found' })).toBeInTheDocument()
    expect(screen.getByText(/is not part of Workflow/)).toBeInTheDocument()
    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpan).toBeNull()
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.stateEventScrollTarget).toBeNull()

    await act(async () => {
      await router.navigate(`${nestedWorkflowRoute}/${differentSubflowSpan.span_id}`)
    })
    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpan?.span_id)
        .toBe(differentSubflowSpan.span_id)
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.stateEventScrollTarget).toBeNull()

    await act(async () => {
      await router.navigate(basicWorkflowRoute)
    })
    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpan?.span_id)
        .toBe(basicWorkflow.span_id)
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.stateEventScrollTarget).toBeNull()
  })

  it('shows a strict error and clears stale state for a fresh invalid child URL', async () => {
    const basicSpans = loadSpans('basic_workflow_success')
    const subflowSpans = loadSpans('subflow_with_parent_store')
    const subflowWorkflow = findSpan(subflowSpans, '2222222222222221')
    const store = makeStore(basicSpans, subflowSpans)
    const invalidRoute = `/workflows/subflow-service/${subflowWorkflow.trace_id}/${subflowWorkflow.span_id}/ffffffffffffffff`
    const router = createMemoryRouter(
      [
        {
          path: '/workflows/:serviceName/:traceId/:workflowSpanId/:spanId?',
          element: <WorkflowDetailPage />,
        },
      ],
      { initialEntries: [invalidRoute] },
    )

    render(
      <Provider store={store}>
        <RouterProvider router={router} />
      </Provider>,
    )

    expect(await screen.findByRole('heading', { name: 'Span not found' })).toBeInTheDocument()
    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpan).toBeNull()
    })
    expect(store.getState().workflowDetailState.activeStateEvent).toBeNull()
    expect(store.getState().workflowDetailState.stateEventScrollTarget).toBeNull()
  })
})
