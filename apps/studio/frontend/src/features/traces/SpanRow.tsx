import { getSpanDurationString } from '../../util/duration-utils'
import { OtelSpan } from '../otel/schemas/schemas'
import { SpanIconConstructor } from '../workflow-logs/span-lists/determine-span-icon'

interface SpanRowProps {
  span: OtelSpan
  isActiveSpan: boolean
  onClick: (span: OtelSpan) => void
}

export default function SpanRow(props: SpanRowProps) {
  const { span, isActiveSpan, onClick } = props

  const start_time = span.start_time
  const end_time = span.end_time
  const spanDuration = getSpanDurationString(start_time, end_time)

  // Exceptions
  const hasExceptions = span.events_json.some((event) => {
    return event.attributes && event.attributes['exception.type'] !== undefined
  })

  return (
    <div className="p-1">
      <div className="flex gap-x-1 items-center">
        <SpanIconConstructor span={span} active={isActiveSpan} />
        <div
          className={`w-full flex gap-x-2 justify-between items-end cursor-pointer rounded-sm px-1 ${isActiveSpan ? 'bg-amber-100 dark:bg-amber-900' : 'hover:bg-zinc-100'}`}
          onClick={() => onClick(span)}
        >
          <div className={'flex gap-x-2 items-center'}>
            <span>{span.name}</span>

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
