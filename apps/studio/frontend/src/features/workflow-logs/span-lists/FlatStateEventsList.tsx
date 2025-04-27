import { PlayIcon } from '@heroicons/react/24/solid'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllWorkflowChildSpans, selectAllWorkflowStateEvents } from '../../otel/store/selectors'
import { useEffect, useMemo, useRef } from 'react'
import { formatMicrosecondsSinceEpochToTime } from '../../../util/duration-utils'

interface FlatStateEventsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function FlatStateEventsList(props: FlatStateEventsListProps) {
  const { serviceName, workflowSpanID } = props
  const scrollableContainerRef = useRef<HTMLDivElement>(null)

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
          block: 'nearest',
          inline: 'nearest',
        })
      }
    }
  }, [scrollToStateEventId])

  return (
    <div ref={scrollableContainerRef} className={'flex flex-col text-sm'}>
      {events.map((event) => {
        const atts = event.attributes
        const eventTime = formatMicrosecondsSinceEpochToTime(event.timeUnixNano / 1000)
        const span = spans.find((span) => span.events_json.some((s) => s.attributes?.id === atts.id))
        const isActivePatch = atts.id === scrollToStateEventId

        return (
          <div
            key={atts.id}
            id={`flat-state-patch-${atts.id}`}
            className={`px-1 py-2 flex justify-between items-start border-b last:border-0 border-zinc-200 dark:border-zinc-700 ${isActivePatch ? 'bg-amber-100 dark:bg-amber-950' : ''}`}
          >
            <div className={'flex gap-x-1 items-start'}>
              <PlayIcon className={'size-4 text-orange-300 mt-0.5'} />

              <div className={'font-normal'}>
                <div className={'leading-tight mb-1'}>
                  {atts['junjo.store.name']} &rarr; {atts['junjo.store.action']}
                </div>
                <div className={'text-xs'}>Node: {span?.name}</div>
                <div className={'opacity-50 text-xs'}>Patch: {atts.id}</div>
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
