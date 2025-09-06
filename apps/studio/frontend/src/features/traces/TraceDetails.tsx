import { useParams } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../otel/schemas/schemas'
import { API_HOST } from '../../config'

export default function TraceDetails() {
  const { traceId } = useParams<{ traceId: string }>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [spans, setSpans] = useState<OtelSpan[]>([])

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
      <div className="grow overflow-scroll">
        <pre>{JSON.stringify(spans, null, 2)}</pre>
      </div>
    </div>
  )
}
