import { useRef } from 'react'
import { useAppDispatch } from '../../../root-store/hooks'
import { OtelSpan } from '../../traces/schemas/schemas'
import { SpanIconConstructor } from '../span-lists/determine-span-icon'
import { spanSelection, WorkflowDetailStateActions } from './store/slice'
import { wrapSpan } from '../../traces/utils/span-accessor'

interface SpanFailuresListProps {
  spans: OtelSpan[]
}

interface FailureDetail {
  key: string
  label: string
  message: string
  stacktrace?: string
  errorType?: string
}

export default function SpanFailuresList(props: SpanFailuresListProps) {
  const { spans } = props
  const scrollableContainerRef = useRef<HTMLDivElement>(null)
  const dispatch = useAppDispatch()

  if (spans.length === 0) {
    return <div className={'p-2'}>Select a span to view any failures.</div>
  }

  return (
    <div ref={scrollableContainerRef} className={'flex flex-col pb-10'}>
      {spans.map((span) => {
        const accessor = wrapSpan(span)
        const failureDetails: FailureDetail[] = [
          ...accessor.exceptionEvents.map((event) => ({
            key: `exception-${event.timeUnixNano}`,
            label: 'Exception',
            message: event.attributes['exception.message'] ?? 'No exception message provided.',
            stacktrace: event.attributes['exception.stacktrace'],
            errorType: event.attributes['exception.type'],
          })),
          ...accessor.hookErrorEvents.map((event) => ({
            key: `hook-${event.timeUnixNano}`,
            label: 'Hook Failure',
            message: event.attributes['junjo.hook.error.message'],
            stacktrace: event.attributes['exception.stacktrace'],
            errorType: event.attributes['junjo.hook.error.type'],
          })),
        ]

        if (failureDetails.length === 0 && accessor.errorType) {
          failureDetails.push({
            key: `span-error-${span.span_id}`,
            label: 'Span Failure',
            message: span.status_message || accessor.errorType,
            errorType: accessor.errorType,
          })
        }

        return (
          <div key={`span-failure-wrap-${span.span_id}`} className={'px-1 pt-2 pb-5 mb-4'}>
            <div className={'flex gap-x-2 items-center'}>
              <SpanIconConstructor span={span} active={false} />
              <button
                className={'font-bold cursor-pointer text-left hover:underline'}
                onClick={() => {
                  dispatch(WorkflowDetailStateActions.selectSpan(spanSelection(span)))
                  dispatch(WorkflowDetailStateActions.setActiveStateEvent(null))
                  dispatch(WorkflowDetailStateActions.setOpenFailuresTrigger())
                }}
              >
                {span.name}
              </button>
            </div>
            {failureDetails.map((failure) => {
              return (
                <div
                  key={failure.key}
                  className={
                    'text-sm px-4.5 mt-1 mb-5 pb-5 pt-1 border-l ml-[9.5px] border-b last:border-b-0 border-zinc-300 dark:border-zinc-700'
                  }
                >
                  <div className={'font-bold'}>{failure.label}</div>
                  {failure.errorType && (
                    <div className={'mt-1'}>
                      <div className={'font-bold'}>Type</div>
                      <div
                        className={
                          'whitespace-pre-wrap font-mono word-break text-zinc-600 dark:text-zinc-400 text-xs'
                        }
                      >
                        {failure.errorType}
                      </div>
                    </div>
                  )}
                  <div className={'mt-2 font-bold'}>Message</div>
                  <div
                    className={
                      'whitespace-pre-wrap font-mono word-break text-zinc-600 dark:text-zinc-400 text-xs'
                    }
                  >
                    {failure.message}
                  </div>
                  {failure.stacktrace && (
                    <>
                      <div className={'h-4'}></div>
                      <div className={'font-bold'}>Stack trace</div>
                      <div
                        className={
                          'whitespace-pre-wrap font-mono word-break text-zinc-600 dark:text-zinc-400 text-xs'
                        }
                      >
                        {failure.stacktrace}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}
