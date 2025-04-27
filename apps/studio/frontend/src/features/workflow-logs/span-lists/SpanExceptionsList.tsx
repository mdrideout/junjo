import { useRef } from 'react'
import { useAppDispatch } from '../../../root-store/hooks'
import { OtelSpan } from '../../otel/store/schemas'

interface SpanExceptionsListProps {
  span: OtelSpan | null | undefined
}

export default function SpanExceptionsList(props: SpanExceptionsListProps) {
  const { span } = props
  const scrollableContainerRef = useRef<HTMLDivElement>(null)
  const dispatch = useAppDispatch()

  if (!span) {
    return <div className={'p-2'}>Select a span to view any exceptions.</div>
  }

  const exceptions =
    span.events_json.filter((event) => {
      return event.attributes && event.attributes['exception.type'] !== undefined
    }) ?? []
  console.log('Exceptions:', exceptions)

  return (
    <div ref={scrollableContainerRef} className={'flex flex-col text-sm pb-10'}>
      {exceptions.length === 0 && <div className={'p-2'}>No exceptions found.</div>}
      {exceptions.map((exception, index) => (
        <div
          key={`${index}-${exception.timeUnixNano}`}
          className={'px-2 py-6 border-b last:border-0 border-zinc-300 dark:border-zinc-700'}
        >
          <div className={'font-bold'}>Message</div>
          <div className={'whitespace-pre-wrap font-mono word-break text-zinc-600 text-xs'}>
            {exception.attributes['exception.message']}
          </div>
          <div className={'h-4'}></div>
          <div className={'font-bold'}>Stack trace</div>
          <div className={'whitespace-pre-wrap font-mono word-break text-zinc-600 text-xs'}>
            {exception.attributes['exception.stacktrace']}
          </div>
        </div>
      ))}
    </div>
  )
}
