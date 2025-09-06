import { useNavigate } from 'react-router'
import { getSpanDurationString } from '../../util/duration-utils'
import { OtelSpan } from '../otel/schemas/schemas'

interface Props {
  trace: OtelSpan
}

export default function TraceListItem({ trace }: Props) {
  const navigate = useNavigate()

  const startString = new Date(trace.start_time).toLocaleString()
  const durationString = getSpanDurationString(trace.start_time, trace.end_time)

  return (
    <tr
      key={trace.span_id}
      className={
        'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
      }
      onClick={() => navigate(`/traces/${trace.service_name}/${trace.trace_id}`)}
    >
      <td className="px-4 py-1.5">{trace.name}</td>
      <td className="px-4 py-1.5 font-mono">{trace.trace_id}</td>
      <td className="px-4 py-1.5 font-mono">{startString}</td>
      <td className="px-4 py-1.5 text-right font-mono">{durationString}</td>
    </tr>
  )
}
