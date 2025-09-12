import { Link, useParams, useNavigate } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../otel/schemas/schemas'
import { API_HOST } from '../../config'
import NestedOtelSpans from './NestedOtelSpans'
import SpanAttributesPanel from './SpanAttributesPanel'

export default function TraceDetails() {
  const { traceId, serviceName, spanId } = useParams<{
    traceId: string
    serviceName: string
    spanId?: string
  }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [spans, setSpans] = useState<OtelSpan[]>([])
  const [selectedSpan, setSelectedSpan] = useState<OtelSpan | null>(null)

  useEffect(() => {
    const fetchSpans = async () => {
      try {
        setLoading(true)
        setError(false)
        const response = await fetch(`${API_HOST}/otel/trace/${traceId}/nested-spans`, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error('Failed to fetch spans')
        }
        const data = await response.json()
        setSpans(data)
        console.log(data)
      } catch (error) {
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    fetchSpans()
  }, [traceId])

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

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div>Error loading spans.</div>
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
        <div className={'text-zinc-400 text-xs'}>{spans[0].start_time}</div>
      </div>
      <div className={'grow overflow-scroll'}>
        <hr className={'my-6'} />
        <div className="grow flex overflow-hidden">
          <div className="w-2/3 overflow-y-auto">
            <NestedOtelSpans
              spans={spans}
              traceId={traceId!}
              selectedSpanId={selectedSpan?.span_id || null}
              onSelectSpan={setSelectedSpan}
            />
          </div>
          <div className="w-1/3 border-l border-zinc-300 dark:border-zinc-700 overflow-y-auto">
            <SpanAttributesPanel span={selectedSpan} />
          </div>
        </div>
      </div>
    </div>
  )
}
