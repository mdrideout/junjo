import { Link, useParams, useNavigate } from 'react-router'
import { useEffect, useRef, useState } from 'react'
import { OtelSpan } from '../traces/schemas/schemas'
import NestedOtelSpans from './NestedOtelSpans'
import SpanAttributesPanel from './SpanAttributesPanel'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { TracesStateActions } from './store/slice'
import {
  selectTraceEvidenceRequestForTraceId,
  selectTraceSpansForTraceId,
} from './store/selectors'
import { logsPath, tracesPath } from '../../util/telemetry-paths'

interface TraceDetailsProps {
  routeIdentity?: {
    traceId: string
    serviceName: string
    spanId?: string
  }
}

export default function TraceDetails({ routeIdentity }: TraceDetailsProps = {}) {
  const routeParameters = useParams<{
    traceId: string
    serviceName: string
    spanId?: string
  }>()
  const { traceId, serviceName, spanId } = routeIdentity ?? routeParameters
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const detailColumnRef = useRef<HTMLDivElement>(null)
  const spans: OtelSpan[] = useAppSelector((state) => selectTraceSpansForTraceId(state, { traceId }))
  const request = useAppSelector((state) =>
    selectTraceEvidenceRequestForTraceId(state, { traceId }),
  )
  const resolverIdentity = routeIdentity === undefined
    ? null
    : JSON.stringify([serviceName, traceId, spanId])
  const [resolverSelection, setResolverSelection] = useState<{
    resolverIdentity: string
    spanId: string
  } | null>(null)
  const [failureFocus, setFailureFocus] = useState<{
    spanId: string
    trigger: number
  } | null>(null)
  const selectedSpanId = routeIdentity === undefined
    ? spanId
    : resolverSelection?.resolverIdentity === resolverIdentity
      ? resolverSelection.spanId
      : spanId
  const selectedSpan = selectedSpanId === undefined
    ? null
    : spans.find((span) => span.span_id === selectedSpanId) ?? null

  useEffect(() => {
    if (!traceId) return
    if (spans.length > 0) return
    dispatch(TracesStateActions.fetchTraceEvidence({ traceId }))
  }, [dispatch, traceId, spans.length])

  const selectSpan = (span: OtelSpan, detailTarget: 'top' | 'failure' = 'top') => {
    if (detailTarget === 'top') {
      setFailureFocus(null)
      if (detailColumnRef.current !== null) detailColumnRef.current.scrollTop = 0
    }
    if (routeIdentity !== undefined && resolverIdentity !== null) {
      setResolverSelection({ resolverIdentity, spanId: span.span_id })
      return
    }
    navigate(tracesPath(serviceName ?? '', traceId, span.span_id), { replace: true })
  }

  const openSpanFailures = (span: OtelSpan) => {
    selectSpan(span, 'failure')
    setFailureFocus((current) => ({
      spanId: span.span_id,
      trigger: (current?.trigger ?? 0) + 1,
    }))
  }

  if (!traceId || !serviceName) {
    return <div>Invalid trace URL.</div>
  }

  const isLoading = spans.length === 0 && request.loading
  const hasError = request.error && spans.length === 0

  if (isLoading) {
    return <div>Loading...</div>
  }

  if (hasError) {
    return <div>Error loading spans.</div>
  }

  if (spans.length === 0) {
    return <div>No spans found.</div>
  }

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <Link to={logsPath(serviceName)} className={'hover:underline'}>
            {serviceName}
          </Link>
          <div>&rarr;</div>
          <Link to={tracesPath(serviceName)} className={'hover:underline'}>
            Traces
          </Link>
          <div>&rarr;</div>
          <div>{traceId}</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>{spans[0]?.start_time}</div>
      </div>
      <div className={'flex min-h-0 grow flex-col'}>
        <hr className={'my-6 shrink-0'} />
        <div className="flex min-h-0 grow overflow-hidden">
          <div
            role="region"
            aria-label="Trace spans"
            className="min-h-0 w-2/3 overflow-y-auto"
          >
            <NestedOtelSpans
              spans={spans}
              traceId={traceId}
              selectedSpanId={selectedSpan?.span_id || null}
              onSelectSpan={selectSpan}
              onOpenFailures={openSpanFailures}
            />
          </div>
          <div
            ref={detailColumnRef}
            role="region"
            aria-label="Selected span details"
            className="min-h-0 w-1/3 overflow-y-auto border-l border-zinc-300 dark:border-zinc-700"
          >
            <SpanAttributesPanel
              span={selectedSpan}
              focusFailuresTrigger={
                failureFocus !== null && failureFocus.spanId === selectedSpan?.span_id
                  ? failureFocus.trigger
                  : null
              }
            />
          </div>
        </div>
      </div>
    </div>
  )
}
