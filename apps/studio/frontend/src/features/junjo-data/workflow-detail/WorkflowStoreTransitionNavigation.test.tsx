import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { configureStore } from '@reduxjs/toolkit'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { describe, expect, it, vi } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import FlatStateEventsList from '../span-lists/FlatStateEventsList'
import {
  BackendWorkflowStoreProjectionFixtureListSchema,
  type WorkflowStoreDiagnostic,
} from '../../workflow-executions/schemas/workflow-store-diagnostic'
import {
  JunjoSetStateEventSchema,
  OtelSpanSchema,
  type OtelSpan,
} from '../../traces/schemas/schemas'
import tracesSlice from '../../traces/store/slice'
import workflowDetailSlice from './store/slice'
import WorkflowStateEventNavButtons from './WorkflowStateDiffNavButtons'
import {
  rawStateEventIdentity,
  type StateEventIdentity,
  type StateEventSelection,
} from './state-event-identity'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const workflowProjectionPath = path.resolve(
  testDirectory,
  '../../workflow-executions/testing/workflow-store-projections.json',
)

function loadCase(): { spans: OtelSpan[]; diagnostic: WorkflowStoreDiagnostic } {
  const fixture = loadJunjoTransportFixtureCase('basic_workflow_success')
  const spans = OtelSpanSchema.array().parse(structuredClone(fixture.spans))
  const eventSpans = spans.filter((span) => span.events_json.length > 0)
  eventSpans[0].events_json[0].timeUnixNano = '1775390400990000000'
  eventSpans[1].events_json[0].timeUnixNano = '1775390400010000000'

  const projections = BackendWorkflowStoreProjectionFixtureListSchema.parse(
    JSON.parse(fs.readFileSync(workflowProjectionPath, 'utf8')),
  )
  const projection = projections.find(
    (candidate) => candidate.case_name === 'basic_workflow_success:1111111111111111',
  )
  if (projection === undefined) throw new Error('Basic Workflow projection missing')
  const diagnostic = structuredClone(projection.detail)
  diagnostic.state.transitions.reverse()
  return { spans, diagnostic }
}

function findStateEvent(spans: OtelSpan[], eventId: string): StateEventSelection {
  for (const span of spans) {
    for (const event of span.events_json) {
      const parsed = JunjoSetStateEventSchema.safeParse(event)
      if (parsed.success && parsed.data.attributes.id === eventId) {
        return {
          ...rawStateEventIdentity(span.span_id, parsed.data),
          event: parsed.data,
        }
      }
    }
  }
  throw new Error(`State event ${eventId} missing`)
}

function makeStore(spans: OtelSpan[], stateEventScrollTarget: StateEventIdentity | null = null) {
  const workflowSpan = spans.find((span) => span.span_id === '1111111111111111')
  const firstEventSpan = spans.find((span) => span.span_id === '1111111111111112')
  if (workflowSpan === undefined || firstEventSpan === undefined) {
    throw new Error('Expected Workflow fixture spans')
  }

  return configureStore({
    reducer: {
      workflowDetailState: workflowDetailSlice,
      tracesState: tracesSlice,
    },
    preloadedState: {
      workflowDetailState: {
        activeSpan: firstEventSpan,
        activeStateEvent: findStateEvent(spans, 'state-event-basic-01'),
        stateEventScrollTarget,
        openFailuresTrigger: null,
      },
      tracesState: {
        serviceNames: { data: [], loading: false, error: false },
        traceSpans: { [workflowSpan.trace_id]: spans },
        loading: false,
        error: false,
      },
    },
  })
}

describe('Workflow Store transition navigation', () => {
  it('navigates by backend transition sequence even when raw timestamps and response order disagree', async () => {
    const user = userEvent.setup()
    const { spans, diagnostic } = loadCase()
    const store = makeStore(spans)

    render(
      <Provider store={store}>
        <WorkflowStateEventNavButtons
          traceId={diagnostic.trace_id}
          storeId={diagnostic.state.store_id}
          transitions={diagnostic.state.transitions}
        />
      </Provider>,
    )

    expect(screen.getByText('(1 / 2)')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next Store transition' }))

    expect(store.getState().workflowDetailState.activeStateEvent?.event.attributes.id)
      .toBe('state-event-basic-02')
    expect(store.getState().workflowDetailState.activeStateEvent?.storeId)
      .toBe('store-basic-01')
    expect(store.getState().workflowDetailState.activeStateEvent?.spanId)
      .toBe('1111111111111113')
    expect(store.getState().workflowDetailState.activeSpan?.span_id)
      .toBe('1111111111111113')
  })

  it('renders the flat state list in backend transition sequence order', () => {
    const { spans, diagnostic } = loadCase()
    const store = makeStore(spans)

    render(
      <Provider store={store}>
        <FlatStateEventsList
          traceId={diagnostic.trace_id}
          workflowSpanId={diagnostic.workflow_span_id}
          storeDiagnosticRequest={{ data: diagnostic, loading: false, error: null }}
        />
      </Provider>,
    )

    const transitionRows = screen.getAllByRole('button')
    expect(transitionRows.map((row) => [
      row.getAttribute('data-state-event-id'),
      row.getAttribute('data-state-event-span-id'),
      row.getAttribute('data-state-event-sequence'),
    ])).toEqual([
      ['state-event-basic-01', '1111111111111112', '1'],
      ['state-event-basic-02', '1111111111111113', '2'],
    ])
  })

  it('selects the matching Store when event IDs collide within the same carrier span', async () => {
    const user = userEvent.setup()
    const { spans, diagnostic } = loadCase()
    const secondEventSpan = spans.find((span) => span.span_id === '1111111111111113')
    if (secondEventSpan === undefined) throw new Error('Second state event span missing')

    const collidingEvent = structuredClone(secondEventSpan.events_json[0])
    collidingEvent.attributes['junjo.store.id'] = 'unrelated-store'
    collidingEvent.attributes['junjo.store.name'] = 'UnrelatedStore'
    secondEventSpan.events_json.push(collidingEvent)
    const store = makeStore(spans)

    render(
      <Provider store={store}>
        <WorkflowStateEventNavButtons
          traceId={diagnostic.trace_id}
          storeId={diagnostic.state.store_id}
          transitions={diagnostic.state.transitions}
        />
      </Provider>,
    )

    await user.click(screen.getByRole('button', { name: 'Next Store transition' }))

    const selected = store.getState().workflowDetailState.activeStateEvent
    expect(selected?.eventId).toBe('state-event-basic-02')
    expect(selected?.spanId).toBe('1111111111111113')
    expect(selected?.storeId).toBe('store-basic-01')
    expect(selected?.event.attributes['junjo.store.name']).toBe('BasicWorkflowState')
  })

  it('scrolls to event IDs containing CSS metacharacters without selector parsing', async () => {
    const user = userEvent.setup()
    const { spans, diagnostic } = loadCase()
    const unusualEventId = 'state:event.[#2]'
    const secondTransition = diagnostic.state.transitions.find(
      (transition) => transition.sequence === 2,
    )
    const secondEventSpan = spans.find((span) => span.span_id === '1111111111111113')
    if (secondTransition === undefined) throw new Error('Second Store transition missing')
    if (secondEventSpan === undefined) throw new Error('Second state event span missing')
    secondTransition.event_id = unusualEventId
    secondEventSpan.events_json[0].attributes.id = unusualEventId

    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      'scrollIntoView',
    )
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    try {
      const store = makeStore(spans)
      render(
        <Provider store={store}>
          <WorkflowStateEventNavButtons
            traceId={diagnostic.trace_id}
            storeId={diagnostic.state.store_id}
            transitions={diagnostic.state.transitions}
          />
          <FlatStateEventsList
            traceId={diagnostic.trace_id}
            workflowSpanId={diagnostic.workflow_span_id}
            storeDiagnosticRequest={{ data: diagnostic, loading: false, error: null }}
          />
        </Provider>,
      )

      await user.click(screen.getByRole('button', { name: 'Next Store transition' }))

      await waitFor(() => expect(scrollIntoView).toHaveBeenCalledOnce())
      expect(store.getState().workflowDetailState.activeStateEvent?.eventId)
        .toBe(unusualEventId)
    } finally {
      if (originalScrollIntoView === undefined) {
        Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
      } else {
        Object.defineProperty(
          HTMLElement.prototype,
          'scrollIntoView',
          originalScrollIntoView,
        )
      }
    }
  })
})
