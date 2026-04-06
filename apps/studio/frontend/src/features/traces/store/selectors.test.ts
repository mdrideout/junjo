import { describe, expect, it } from 'vitest'
import { loadJunjoTransportFixtureCase } from '../../../test-utils/junjo-fixture-loader'
import { store, RootState } from '../../../root-store/store'
import { JunjoSetStateEvent, JunjoSetStateEventSchema, OtelSpan, OtelSpanSchema } from '../schemas/schemas'
import {
  identifySpanWorkflowChain,
  selectActiveStoreID,
  selectStateEventsByJunjoStoreId,
  selectTraceFailureSpans,
  selectWorkflowSpanByStoreId,
} from './selectors'

function loadFixtureSpans(caseName: string): OtelSpan[] {
  const fixture = loadJunjoTransportFixtureCase(caseName)
  return OtelSpanSchema.array().parse(fixture.spans)
}

function findSpan(spans: OtelSpan[], spanId: string): OtelSpan {
  const span = spans.find((candidate) => candidate.span_id === spanId)
  if (!span) {
    throw new Error(`Expected span ${spanId} in fixture`)
  }

  return span
}

function findSetStateEvent(spans: OtelSpan[], eventId: string): JunjoSetStateEvent {
  for (const span of spans) {
    for (const event of span.events_json) {
      const parsed = JunjoSetStateEventSchema.safeParse(event)
      if (parsed.success && parsed.data.attributes.id === eventId) {
        return parsed.data
      }
    }
  }

  throw new Error(`Expected event ${eventId} in fixture`)
}

function buildState({
  spans,
  activeSpanId,
  activeSetStateEventId,
}: {
  spans: OtelSpan[]
  activeSpanId?: string
  activeSetStateEventId?: string
}): RootState {
  const baseState = store.getState()
  const traceId = spans[0]?.trace_id

  return {
    ...baseState,
    tracesState: {
      ...baseState.tracesState,
      traceSpans: traceId ? { [traceId]: spans } : {},
    },
    workflowDetailState: {
      ...baseState.workflowDetailState,
      activeSpan: activeSpanId ? findSpan(spans, activeSpanId) : null,
      activeSetStateEvent: activeSetStateEventId ? findSetStateEvent(spans, activeSetStateEventId) : null,
      openFailuresTrigger: null,
    },
  }
}

describe('trace selectors', () => {
  it('selects failure spans from error.type and hook error events, but not cancelled spans', () => {
    const failedSpans = loadFixtureSpans('failed_executable_with_error_type')
    const failedState = buildState({ spans: failedSpans })
    expect(selectTraceFailureSpans(failedState, { traceId: failedSpans[0].trace_id }).map((span) => span.span_id)).toEqual([
      '4444444444444443',
    ])

    const hookFailureSpans = loadFixtureSpans('hook_failure_on_surrounding_span')
    const hookFailureState = buildState({ spans: hookFailureSpans })
    expect(
      selectTraceFailureSpans(hookFailureState, { traceId: hookFailureSpans[0].trace_id }).map(
        (span) => span.span_id,
      ),
    ).toEqual(['6666666666666662'])

    const cancelledSpans = loadFixtureSpans('cancelled_executable')
    const cancelledState = buildState({ spans: cancelledSpans })
    expect(selectTraceFailureSpans(cancelledState, { traceId: cancelledSpans[0].trace_id })).toEqual([])
  })

  it('builds workflow chains from OTel parent_span_id ancestry', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const state = buildState({
      spans,
      activeSpanId: '2222222222222224',
    })

    const chain = identifySpanWorkflowChain(state, {
      traceId: spans[0].trace_id,
      workflowSpanId: '2222222222222221',
    })

    expect(chain.map((span) => span.span_id)).toEqual(['2222222222222221', '2222222222222223'])
  })

  it('finds workflow spans by current Junjo store.id fields', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const state = buildState({ spans })

    const workflowSpan = selectWorkflowSpanByStoreId(state, {
      traceId: spans[0].trace_id,
      storeId: 'store-subflow-child-01',
    })

    expect(workflowSpan?.span_id).toBe('2222222222222223')
  })

  it('defaults a selected subflow to the subflow store', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const state = buildState({
      spans,
      activeSpanId: '2222222222222223',
    })

    expect(selectActiveStoreID(state)).toBe('store-subflow-child-01')
  })

  it('uses the selected state event store even when a subflow is selected', () => {
    const spans = loadFixtureSpans('subflow_with_parent_store')
    const state = buildState({
      spans,
      activeSpanId: '2222222222222223',
      activeSetStateEventId: 'state-event-subflow-01',
    })

    expect(selectActiveStoreID(state)).toBe('store-subflow-child-01')
  })

  it('selects state events by junjo.store.id using the current event contract', () => {
    const spans = loadFixtureSpans('basic_workflow_success')
    const state = buildState({ spans })

    const events = selectStateEventsByJunjoStoreId(state, {
      traceId: spans[0].trace_id,
      spanId: '1111111111111111',
      storeId: 'store-basic-01',
    })

    expect(events.map((event) => event.attributes.id)).toEqual(['state-event-basic-01', 'state-event-basic-02'])
  })
})
