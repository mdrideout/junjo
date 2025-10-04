import { useAppDispatch } from '../../../root-store/hooks'
import { getSpanDurationString } from '../../../util/duration-utils'
import { JunjoSpanType, OtelSpan } from '../../traces/schemas/schemas'
import { SpanIconConstructor } from './determine-span-icon'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'
import { spanNameConstructor } from './span-name-constructor'

interface NestedSpanRowProps {
  span: OtelSpan
  isActiveSpan: boolean
}

export default function NestedSpanRow(props: NestedSpanRowProps) {
  const { span, isActiveSpan } = props
  const dispatch = useAppDispatch()

  // Determine the type of span
  const nonJunjoSpan = span.junjo_span_type === JunjoSpanType.OTHER
  const junjoSpan = !nonJunjoSpan

  const start_time = span.start_time
  const end_time = span.end_time
  const spanDuration = getSpanDurationString(start_time, end_time)

  // Exceptions
  const hasExceptions = span.events_json.some((event) => {
    return event.attributes && event.attributes['exception.type'] !== undefined
  })

  // Create the name
  const name = spanNameConstructor(span)

  // console.log('Span attributes: ', span)

  return (
    <div className={`p-1 ${nonJunjoSpan ? 'border-b border-zinc-200 dark:border-zinc-700' : ''}`}>
      <div className={`flex gap-x-2 ${nonJunjoSpan ? 'items-start' : 'items-center'}`}>
        <SpanIconConstructor span={span} active={isActiveSpan} />
        <div className={'w-full flex gap-x-2 justify-between items-end'}>
          <div className={'flex gap-x-2 items-center'}>
            {junjoSpan && (
              <div className={'flex gap-x-2 items-center'}>
                <button
                  className={`cursor-pointer text-left hover:underline`}
                  onClick={() => {
                    console.log('Clicked span:', span.name)
                    dispatch(WorkflowDetailStateActions.handleSetActiveSpan(span))
                  }}
                >
                  {name}
                </button>
              </div>
            )}

            {nonJunjoSpan && (
              <button
                className={`cursor-pointer text-left hover:underline`}
                onClick={() => {
                  console.log('Clicked span:', span.name)
                  dispatch(WorkflowDetailStateActions.handleSetActiveSpan(span))
                }}
              >
                {name}
              </button>
            )}

            {hasExceptions && (
              // <ExclamationTriangleIcon className={'mt-1 size-4 text-red-700 dark:text-red-300'} />
              <button
                className={
                  'mt-[1px] cursor-pointer text-white bg-red-700 hover:bg-red-600 rounded-lg px-1.5 text-xs'
                }
                onClick={() => {
                  // Set this span as the active span
                  dispatch(WorkflowDetailStateActions.setActiveSpan(span))

                  // Set this exception as the active
                  dispatch(WorkflowDetailStateActions.setOpenExceptionsTrigger())
                }}
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
