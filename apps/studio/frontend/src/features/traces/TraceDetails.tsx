import { Link, useParams, useNavigate } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../traces/schemas/schemas'
import NestedOtelSpans from './NestedOtelSpans'
import SpanAttributesPanel from './SpanAttributesPanel'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { TracesStateActions } from './store/slice'
import { selectTraceSpansForTraceId, selectTracesError, selectTracesLoading } from './store/selectors'

export default function TraceDetails() {
  const { traceId, serviceName, spanId } = useParams<{
    traceId: string
    serviceName: string
    spanId?: string
  }>()
  const navigate = useNavigate()
  const dispatch = useAppDispatch()
  const spans: OtelSpan[] = useAppSelector((state) => selectTraceSpansForTraceId(state, { traceId }))
  const loading = useAppSelector(selectTracesLoading)
  const error = useAppSelector(selectTracesError)
  const [selectedSpan, setSelectedSpan] = useState<OtelSpan | null>(null)
  const [requestedTraceId, setRequestedTraceId] = useState<string | null>(null)

  useEffect(() => {
    if (!traceId) return
    if (spans.length > 0) return
    if (requestedTraceId === traceId) return
    dispatch(TracesStateActions.fetchSpansByTraceId({ traceId }))
    setRequestedTraceId(traceId)
  }, [dispatch, traceId, spans.length, requestedTraceId])

  useEffect(() => {
    if (spanId && spans.length > 0) {
      const span = spans.find((s) => s.span_id === spanId)
      if (span) {
        setSelectedSpan(span)
      }
    }
  }, [spanId, spans])

  useEffect(() => {
    if (selectedSpan) {
      navigate(`/traces/${serviceName}/${traceId}/${selectedSpan.span_id}`, {
        replace: true,
      })
    }
  }, [selectedSpan, navigate, serviceName, traceId])

  if (!traceId || !serviceName) {
    return <div>Invalid trace URL.</div>
  }

  const isLoading = spans.length === 0 && (loading || requestedTraceId !== traceId)
  const hasError = Boolean(error) && spans.length === 0

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
          <Link to={`/logs/${serviceName}`} className={'hover:underline'}>
            {serviceName}
          </Link>
          <div>&rarr;</div>
          <Link to={`/traces/${serviceName}`} className={'hover:underline'}>
            Traces
          </Link>
          <div>&rarr;</div>
          <div>{traceId}</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>{spans[0]?.start_time}</div>
      </div>
      <div className={'grow overflow-scroll'}>
        <hr className={'my-6'} />
        <div className="grow flex overflow-hidden">
          <div className="w-2/3 overflow-y-auto">
            <NestedOtelSpans
              spans={spans}
              traceId={traceId}
              selectedSpanId={selectedSpan?.span_id || null}
              onSelectSpan={setSelectedSpan}
            />
          </div>
          <div className="w-1/3 border-l border-zinc-300 dark:border-zinc-700 overflow-y-auto">
            <SpanAttributesPanel span={selectedSpan} origin="traces" />
          </div>
        </div>
      </div>
    </div>
  )
}
