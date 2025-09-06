import { MagnifyingGlassIcon } from '@radix-ui/react-icons'
import { getSpanDurationString } from '../../util/duration-utils'
import { OtelSpan } from '../otel/schemas/schemas'
import { Link } from 'react-router'

interface SpanRowProps {
  span: OtelSpan
  isActiveSpan: boolean
}

export default function SpanRow(props: SpanRowProps) {
  const { span, isActiveSpan } = props

  const start_time = span.start_time
  const end_time = span.end_time
  const spanDuration = getSpanDurationString(start_time, end_time)

  // Exceptions
  const hasExceptions = span.events_json.some((event) => {
    return event.attributes && event.attributes['exception.type'] !== undefined
  })

  // Create Jaeger Deep Link to the span
  const traceId = span.trace_id
  const spanId = span.span_id
  const jaegerDeepLink = `${window.location.protocol}//${window.location.hostname}/jaeger/trace/${traceId}?uiFind=${spanId}`

  // Span name
  const name = span.name

  return (
    <div className="p-1">
      <div className="flex gap-x-2 items-center">
        <div className="w-4 h-4 rounded-full bg-blue-500"></div>
        <div className={'w-full flex gap-x-2 justify-between items-end'}>
          <div className={'flex gap-x-2 items-center'}>
            <span>{name}</span>
            <Link to={jaegerDeepLink} target={'_blank'} title={'Open in Jaeger'}>
              <MagnifyingGlassIcon className={'size-4 cursor-pointer'} />
            </Link>

            {hasExceptions && (
              <button
                className={
                  'mt-[1px] cursor-pointer text-white bg-red-700 hover:bg-red-600 rounded-lg px-1.5 text-xs'
                }
              >
                exceptions
              </button>
            )}
          </div>

          <div className={'font-mono text-zinc-500 text-xs'}>{spanDuration}</div>
        </div>
      </div>
    </div>
  )
}
