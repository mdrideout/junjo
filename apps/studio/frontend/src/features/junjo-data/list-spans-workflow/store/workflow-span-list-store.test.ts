import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createAppStore } from '../../../../root-store/store'
import type { OtelSpan } from '../../../traces/schemas/schemas'
import { getSpansTypeWorkflow } from '../fetch/get-spans-type-workflow'
import { selectNextWorkflowSpan, selectWorkflowSpanListRequest } from './selectors'
import { WorkflowExecutionsStateActions } from './slice'

vi.mock('../fetch/get-spans-type-workflow', () => ({
  getSpansTypeWorkflow: vi.fn(),
}))

function workflowSpan(serviceName: string, spanId: string): OtelSpan {
  return {
    trace_id: spanId.repeat(2),
    span_id: spanId,
    parent_span_id: null,
    service_name: serviceName,
    name: `${serviceName} Workflow`,
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
    resource_attributes_json: { 'service.name': serviceName },
    resource_dropped_attributes_count: 0,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe('Workflow span list state', () => {
  const getWorkflowSpans = vi.mocked(getSpansTypeWorkflow)

  beforeEach(() => {
    getWorkflowSpans.mockReset()
  })

  it('keeps the URL service result current when an earlier service resolves late', async () => {
    const store = createAppStore()
    const serviceAResponse = deferred<OtelSpan[]>()
    const serviceASpan = workflowSpan('service-a', 'aaaaaaaaaaaaaaaa')
    const serviceBSpans = [
      workflowSpan('service-b', 'bbbbbbbbbbbbbbbb'),
      workflowSpan('service-b', 'cccccccccccccccc'),
    ]
    getWorkflowSpans.mockImplementation((serviceName) =>
      serviceName === 'service-a' ? serviceAResponse.promise : Promise.resolve(serviceBSpans),
    )

    store.dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow('service-a'))
    store.dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow('service-b'))

    await waitFor(() => {
      expect(selectWorkflowSpanListRequest(store.getState(), 'service-b')).toMatchObject({
        workflowSpanList: serviceBSpans,
        loading: false,
        error: null,
      })
    })

    serviceAResponse.resolve([serviceASpan])
    await serviceAResponse.promise

    expect(store.getState().workflowSpanListState.listServiceName).toBe('service-b')
    expect(selectWorkflowSpanListRequest(store.getState(), 'service-b').workflowSpanList).toEqual(
      serviceBSpans,
    )
    expect(selectWorkflowSpanListRequest(store.getState(), 'service-a')).toMatchObject({
      workflowSpanList: [],
      loading: true,
      error: null,
    })
    expect(
      selectNextWorkflowSpan(store.getState(), {
        serviceName: 'service-b',
        spanID: serviceBSpans[0].span_id,
      }),
    ).toEqual(serviceBSpans[1])
    expect(
      selectNextWorkflowSpan(store.getState(), {
        serviceName: 'service-a',
        spanID: serviceBSpans[0].span_id,
      }),
    ).toBeUndefined()
  })

  it('deduplicates repeated requests for the same service while it is loading', async () => {
    const store = createAppStore()
    const spans = [workflowSpan('service-a', 'aaaaaaaaaaaaaaaa')]
    const response = deferred<OtelSpan[]>()
    getWorkflowSpans.mockReturnValue(response.promise)

    store.dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow('service-a'))
    store.dispatch(WorkflowExecutionsStateActions.fetchSpansTypeWorkflow('service-a'))

    expect(getWorkflowSpans).toHaveBeenCalledTimes(1)

    response.resolve(spans)
    await waitFor(() => {
      expect(selectWorkflowSpanListRequest(store.getState(), 'service-a')).toMatchObject({
        workflowSpanList: spans,
        loading: false,
        error: null,
      })
    })
  })
})
