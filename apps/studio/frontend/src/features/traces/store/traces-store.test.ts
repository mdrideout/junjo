import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../../auth/test-utils/mock-server'
import { createAppStore } from '../../../root-store/store'
import type { TraceEvidence } from '../schemas/trace-evidence'
import { TracesStateActions } from './slice'

function emptyEvidence(traceId: string): TraceEvidence {
  return {
    trace_id: traceId,
    spans: [],
    executables_by_span_id: {},
    operations_by_owner_runtime_id: {},
    stores_by_id: {},
    relationships_by_owner_span_id: {},
    diagnostics: [],
  }
}

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

describe('trace evidence request state', () => {
  it('loads a newly selected trace while another trace is in flight and ignores the late status outcome', async () => {
    const traceA = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    const traceB = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    const gateA = deferred()
    const gateB = deferred()
    const requestCounts = new Map<string, number>()

    server.use(
      http.get(`${API_BASE}/api/v1/trace-evidence/:traceId`, async ({ params }) => {
        const traceId = String(params.traceId)
        requestCounts.set(traceId, (requestCounts.get(traceId) ?? 0) + 1)
        if (traceId === traceA) await gateA.promise
        if (traceId === traceB) await gateB.promise
        return HttpResponse.json(emptyEvidence(traceId))
      }),
    )

    const store = createAppStore()
    store.dispatch(TracesStateActions.fetchTraceEvidence({ traceId: traceA }))
    store.dispatch(TracesStateActions.fetchTraceEvidence({ traceId: traceA }))

    await waitFor(() => {
      expect(store.getState().tracesState.traceEvidenceRequest).toEqual({
        traceId: traceA,
        loading: true,
        error: false,
      })
    })

    store.dispatch(TracesStateActions.fetchTraceEvidence({ traceId: traceB }))
    await waitFor(() => {
      expect(store.getState().tracesState.traceEvidenceRequest.traceId).toBe(traceB)
    })

    gateB.resolve()
    await waitFor(() => {
      expect(store.getState().tracesState).toMatchObject({
        traceEvidence: { [traceB]: emptyEvidence(traceB) },
        traceEvidenceRequest: { traceId: traceB, loading: false, error: false },
      })
    })

    gateA.resolve()
    await waitFor(() => {
      expect(store.getState().tracesState.traceEvidence[traceA]).toEqual(emptyEvidence(traceA))
    })

    expect(store.getState().tracesState.traceEvidenceRequest).toEqual({
      traceId: traceB,
      loading: false,
      error: false,
    })
    expect(requestCounts).toEqual(new Map([
      [traceA, 1],
      [traceB, 1],
    ]))
  })
})
