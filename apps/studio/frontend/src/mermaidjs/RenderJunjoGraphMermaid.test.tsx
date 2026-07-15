import { configureStore } from '@reduxjs/toolkit'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import NestedWorkflowSpans from '../features/junjo-data/span-lists/NestedWorkflowSpans'
import workflowDetailSlice, {
  spanSelection,
  WorkflowDetailStateActions,
} from '../features/junjo-data/workflow-detail/store/slice'
import { OtelSpanSchema } from '../features/traces/schemas/schemas'
import tracesSlice from '../features/traces/store/slice'
import { makeTraceEvidence } from '../features/traces/testing/make-trace-evidence'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { JGraphSchema } from '../junjo-graph/schemas'
import { MermaidProvider } from './mermaid-provider'
import { loadJunjoTransportFixtureCase } from '../test-utils/junjo-fixture-loader'
import RenderJunjoGraphMermaid from './RenderJunjoGraphMermaid'

const originalScrollIntoView = Object.getOwnPropertyDescriptor(
  Element.prototype,
  'scrollIntoView',
)

beforeAll(() => {
  Object.defineProperty(SVGElement.prototype, 'getBBox', {
    configurable: true,
    value: vi.fn(() => ({ x: 0, y: 0, width: 100, height: 30 })),
  })
  Object.defineProperty(SVGElement.prototype, 'getComputedTextLength', {
    configurable: true,
    value: vi.fn(() => 80),
  })
})

afterEach(() => {
  if (originalScrollIntoView === undefined) {
    Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
  } else {
    Object.defineProperty(
      Element.prototype,
      'scrollIntoView',
      originalScrollIntoView,
    )
  }
})

describe('RenderJunjoGraphMermaid selection integration', () => {
  it('keeps the real Graph renderer, nested tree, Redux selection, and URL synchronized', async () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })
    const spans = OtelSpanSchema.array().parse(
      loadJunjoTransportFixtureCase('basic_workflow_success').spans,
    )
    const workflowSpan = spans.find((span) => span.span_id === '1111111111111111')
    const fetchSpan = spans.find((span) => span.span_id === '1111111111111112')
    const transformSpan = spans.find((span) => span.span_id === '1111111111111113')
    if (workflowSpan === undefined || fetchSpan === undefined || transformSpan === undefined) {
      throw new Error('Basic Workflow fixture is incomplete')
    }
    const snapshotJson = workflowSpan.attributes_json['junjo.workflow.execution_graph_snapshot']
    if (typeof snapshotJson !== 'string') throw new Error('Workflow Graph snapshot missing')
    const graphSnapshot = JGraphSchema.parse(JSON.parse(snapshotJson))
    const traceId = workflowSpan.trace_id
    const store = configureStore({
      reducer: {
        workflowDetailState: workflowDetailSlice,
        tracesState: tracesSlice,
      },
      preloadedState: {
        workflowDetailState: {
          activeSpanIdentity: spanSelection(workflowSpan),
          activeStateEvent: null,
          stateEventScrollTarget: null,
          openFailuresTrigger: null,
        },
        tracesState: {
          serviceNames: { data: [], loading: false, error: false },
          traceEvidence: { [traceId]: makeTraceEvidence(spans) },
          loading: false,
          error: false,
        },
      },
    })
    const route = `/workflows/basic-service/${traceId}/${workflowSpan.span_id}`
    const router = createMemoryRouter(
      [{
        path: '/workflows/:serviceName/:traceId/:workflowSpanId/:spanId?',
        element: (
          <>
            <RenderJunjoGraphMermaid
              graphSnapshot={graphSnapshot}
              traceId={traceId}
              workflowChain={[workflowSpan]}
              mermaidFlowString={JunjoGraph.fromJson(graphSnapshot).toMermaid()}
              mermaidUniqueId="selection-integration"
              workflowSpanId={workflowSpan.span_id}
            />
            <NestedWorkflowSpans
              traceId={traceId}
              workflowSpanId={workflowSpan.span_id}
            />
          </>
        ),
      }],
      { initialEntries: [route] },
    )

    render(
      <Provider store={store}>
        <MermaidProvider>
          <RouterProvider router={router} />
        </MermaidProvider>
      </Provider>,
    )

    const fetchNode = await waitFor(() => {
      const element = document.querySelector(
        '[data-junjo-graph-node-id="node.basic.fetch_input"]',
      )
      expect(element).not.toBeNull()
      return element as Element
    })
    fireEvent.click(fetchNode)

    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpanIdentity)
        .toEqual(spanSelection(fetchSpan))
      expect(router.state.location.pathname).toBe(`${route}/${fetchSpan.span_id}`)
      expect(document.querySelector(`[data-span-id="${fetchSpan.span_id}"]`))
        .toHaveClass('bg-gradient-to-br')
    })

    fireEvent.click(screen.getByRole('button', { name: 'transform_output' }))

    await waitFor(() => {
      expect(store.getState().workflowDetailState.activeSpanIdentity)
        .toEqual(spanSelection(transformSpan))
      expect(document.querySelector(
        '[data-junjo-graph-node-id="node.basic.transform_output"]',
      )).toHaveClass('mermaid-node-active')
    })

    act(() => {
      store.dispatch(WorkflowDetailStateActions.selectSpan(spanSelection(fetchSpan)))
    })
    await waitFor(() => expect(fetchNode).toHaveClass('mermaid-node-active'))
  })
})
