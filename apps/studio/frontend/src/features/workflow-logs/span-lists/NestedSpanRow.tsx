import { MagnifyingGlassIcon } from '@radix-ui/react-icons'
import { useAppDispatch } from '../../../root-store/hooks'
import { getSpanDurationString } from '../../../util/duration-utils'
import { JunjoSpanType, OtelSpan } from '../../otel/schemas/schemas'
import { SpanIconConstructor } from './determine-span-icon'
import { Link } from 'react-router'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'
import { spanNameConstructor } from './span-name-constructor'

interface NestedSpanRowProps {
  span: OtelSpan
  isActiveSpan: boolean
}

export default function NestedSpanRow(props: NestedSpanRowProps) {
  const { span, isActiveSpan } = props
  const dispatch = useAppDispatch()

  const spanTypeOther = span.junjo_span_type === JunjoSpanType.OTHER

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

  // Create the name
  const name = spanNameConstructor(span)

  console.log('Span attributes: ', span.attributes_json)

  return (
    <div className={`p-1 ${spanTypeOther ? 'border-b border-zinc-200 dark:border-zinc-700' : ''}`}>
      <div className={`flex gap-x-2 ${spanTypeOther ? 'items-start' : 'items-center'}`}>
        <SpanIconConstructor span={span} active={isActiveSpan} />
        <div className={'w-full flex gap-x-2 justify-between items-end'}>
          <div className={'flex gap-x-2 items-center'}>
            {/* Workflow Spans Get Clickable Titles */}
            {!spanTypeOther ? (
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
                <Link to={jaegerDeepLink} target={'_blank'} title={'Open in Jaeger'}>
                  <MagnifyingGlassIcon className={'size-4 cursor-pointer'} />
                </Link>
              </div>
            ) : (
              <div className={'flex gap-x-2 items-center'}>
                <span>{name}</span>
                <Link to={jaegerDeepLink} target={'_blank'} title={'Open in Jaeger'}>
                  <MagnifyingGlassIcon className={'size-4 cursor-pointer'} />
                </Link>
              </div>
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
