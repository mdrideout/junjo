import { useParams } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../otel/schemas/schemas'
import { API_HOST } from '../../config'
import NestedOtelSpans from './NestedOtelSpans'
import SpanAttributesPanel from './SpanAttributesPanel'

export default function TraceDetails() {
  const { traceId } = useParams<{ traceId: string }>()
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

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div>Error loading spans.</div>
  }

  return (
    <div className="h-full flex flex-col">
      <h1>Trace Details</h1>
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
  )
}
