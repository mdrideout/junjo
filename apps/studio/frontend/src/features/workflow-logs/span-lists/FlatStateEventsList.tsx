import { PlayIcon } from '@heroicons/react/24/solid'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllWorkflowChildSpans, selectAllWorkflowStateEvents } from '../../otel/store/selectors'
import { useEffect, useMemo, useRef } from 'react'
import { formatMicrosecondsSinceEpochToTime } from '../../../util/duration-utils'
import { SpanIconConstructor } from './determine-span-icon'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'

interface FlatStateEventsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function FlatStateEventsList(props: FlatStateEventsListProps) {
  const { serviceName, workflowSpanID } = props
  const scrollableContainerRef = useRef<HTMLDivElement>(null)
  const dispatch = useAppDispatch()

  // Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  const events = useAppSelector((state: RootState) => selectAllWorkflowStateEvents(state, selectorProps))
  const spans = useAppSelector((state: RootState) => selectAllWorkflowChildSpans(state, selectorProps))
  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const scrollToSpanId = useAppSelector((state: RootState) => state.workflowDetailState.scrollToSpanId)
  const scrollToStateEventId = useAppSelector(
    (state: RootState) => state.workflowDetailState.scrollToStateEventId,
  )

  // Sort the events by timeUnixNano
  events.sort((a, b) => {
    const aTime = a.timeUnixNano
    const bTime = b.timeUnixNano
    return aTime - bTime
  })

  // Scroll To State Event
  useEffect(() => {
    if (scrollToStateEventId && scrollableContainerRef.current) {
      const targetStateEventId = `#flat-state-patch-${scrollToStateEventId}`
      console.log(`Scrolling to state event: ${targetStateEventId}`)
      const targetElement = scrollableContainerRef.current.querySelector(targetStateEventId)
      if (targetElement) {
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'center',
        })
      }
    }
  }, [scrollToStateEventId])

  // Scroll To First Matching Node Span
  useEffect(() => {
    if (scrollToSpanId && scrollableContainerRef.current) {
      const targetSpanId = `.flat-span-${scrollToSpanId}`
      console.log(`Scrolling to span: ${targetSpanId}`)
      const targetElement = scrollableContainerRef.current.querySelector(targetSpanId)
      if (targetElement) {
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'center',
        })
      }
    }
  }, [scrollToSpanId])

  return (
    <div ref={scrollableContainerRef} className={'flex flex-col text-sm'}>
      {events.map((event) => {
        const atts = event.attributes
        const eventTime = formatMicrosecondsSinceEpochToTime(event.timeUnixNano / 1000)
        const span = spans.find((span) => span.events_json.some((s) => s.attributes?.id === atts.id))
        const isActivePatch = atts.id === activeSetStateEvent?.attributes.id
        const isActiveSpan = (span && span.span_id === activeSpan?.span_id) ?? false
        const spanClass = span ? `flat-span-${span.span_id}` : ''

        function determineActiveStyle() {
          if (isActivePatch) {
            return 'bg-amber-100 dark:bg-amber-950'
          } else if (isActiveSpan) {
            return 'bg-zinc-100 dark:bg-zinc-800'
          }
          return ''
        }

        return (
          <div
            key={atts.id}
            id={`flat-state-patch-${atts.id}`}
            className={`${spanClass} px-2 py-2 cursor-pointer flex justify-between items-start border-b last:border-0 border-zinc-200 dark:border-zinc-700 ${determineActiveStyle()}`}
            onClick={() => {
              // Set the active span that this state event belongs to
              span && dispatch(WorkflowDetailStateActions.setActiveSpan(span))

              // Set the active set state event
              dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(event))
            }}
          >
            <div className={'flex gap-x-1 items-start'}>
              <div className={'mt-[1px]'}>
                <SpanIconConstructor span={span} active={isActiveSpan} size={'size-3.5'} />
              </div>

              <div className={'font-normal text-xs'}>
                <div className={'mb-0.5 font-bold'}>{span?.name}</div>
                <div className={'flex gap-x-1 items-center'}>
                  <PlayIcon className={'size-3.5 text-orange-300'} /> {atts['junjo.store.name']} &rarr;{' '}
                  {atts['junjo.store.action']}
                </div>

                <div className={'opacity-50 text-xs pl-[18.5px]'}>{atts.id}</div>
              </div>
            </div>
            <div className={'font-mono text-zinc-500 text-xs'}>{eventTime}</div>
          </div>
        )
      })}
      <div className={'h-4'}></div>
    </div>
  )
}
