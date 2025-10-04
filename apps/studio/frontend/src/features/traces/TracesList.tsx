import { useParams } from 'react-router'
import { useEffect, useState } from 'react'
import { OtelSpan } from '../traces/schemas/schemas'
import { API_HOST } from '../../config'
import TraceListItem from './TraceListItem'

export default function TracesList({ filterLLM }: { filterLLM: boolean }) {
  const { serviceName } = useParams<{ serviceName: string }>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [traces, setTraces] = useState<OtelSpan[]>([])

  useEffect(() => {
    const fetchTraces = async () => {
      try {
        setLoading(true)
        setError(false)
        const endpoint = filterLLM
          ? `${API_HOST}/otel/service/${serviceName}/root-spans-filtered`
          : `${API_HOST}/otel/service/${serviceName}/root-spans`
        const response = await fetch(endpoint, {
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error('Failed to fetch traces')
        }
        const data = await response.json()
        setTraces(data)
      } catch (error) {
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    fetchTraces()
  }, [serviceName, filterLLM])

  if (loading) {
    return <div>Loading...</div>
  }

  if (error) {
    return <div>Error loading traces.</div>
  }

  return (
    <table className="text-left text-sm">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Name</th>
          <th className={'px-4 py-1'}>Trace ID</th>
          <th className={'px-4 py-1'}>Start Time</th>
          <th className={'px-4 py-1 text-right'}>Duration</th>
        </tr>
      </thead>
      <tbody>
        {traces.map((trace) => (
          <TraceListItem key={trace.span_id} trace={trace} />
        ))}
      </tbody>
    </table>
  )
}
