import { useRef } from 'react'
import { useAppDispatch } from '../../../root-store/hooks'
import { OtelSpan } from '../../traces/schemas/schemas'
import { SpanIconConstructor } from '../span-lists/determine-span-icon'
import { WorkflowDetailStateActions } from './store/slice'

interface SpanExceptionsListProps {
  spans: OtelSpan[]
}

export default function SpanExceptionsList(props: SpanExceptionsListProps) {
  const { spans } = props
  const scrollableContainerRef = useRef<HTMLDivElement>(null)
  const dispatch = useAppDispatch()

  if (spans.length === 0) {
    return <div className={'p-2'}>Select a span to view any exceptions.</div>
  }

  return (
    <div ref={scrollableContainerRef} className={'flex flex-col pb-10'}>
      {spans.map((span) => {
        const exceptions =
          span.events_json.filter((event) => {
            return event.attributes && event.attributes['exception.type'] !== undefined
          }) ?? []
        console.log('Exceptions:', exceptions)

        return (
          <div key={`span-exception-wrap-${span.span_id}`} className={'px-1 pt-2 pb-5 mb-4'}>
            <div className={'flex gap-x-2 items-center'}>
              <SpanIconConstructor span={span} active={false} />
              <button
                className={'font-bold cursor-pointer text-left hover:underline'}
                onClick={() => {
                  // Set as the active span
                  dispatch(WorkflowDetailStateActions.setActiveSpan(span))

                  // Trigger the node exceptions tab
                  dispatch(WorkflowDetailStateActions.setOpenExceptionsTrigger())
                }}
              >
                {span?.name}
              </button>
            </div>
            {exceptions.map((exception, index) => {
              return (
                <div
                  key={`exception-${index}-${exception.timeUnixNano}`}
                  className={`text-sm px-4.5 mt-1 mb-5 pb-5 pt-1 border-l ml-[9.5px] border-b last:border-b-0 border-zinc-300 dark:border-zinc-700  ${false ? 'border-amber-500' : 'border-zinc-300 dark:border-zinc-700'}`}
                >
                  <div className={'font-bold'}>Message</div>
                  <div
                    className={
                      'whitespace-pre-wrap font-mono word-break text-zinc-600 dark:text-zinc-400 text-xs'
                    }
                  >
                    {exception.attributes['exception.message']}
                  </div>
                  <div className={'h-4'}></div>
                  <div className={'font-bold'}>Stack trace</div>
                  <div
                    className={
                      'whitespace-pre-wrap font-mono word-break text-zinc-600 dark:text-zinc-400 text-xs'
                    }
                  >
                    {exception.attributes['exception.stacktrace']}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}
