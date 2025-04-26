import { PlayIcon } from '@heroicons/react/24/solid'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { selectAllWorkflowChildSpans, selectAllWorkflowStateEvents } from '../../otel/store/selectors'
import { useMemo } from 'react'

interface FlatStateEventsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function FlatStateEventsList(props: FlatStateEventsListProps) {
  const { serviceName, workflowSpanID } = props

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

  console.log('Spans', spans)

  return (
    <div className={'flex flex-col gap-y-4 text-sm'}>
      {events.map((event) => {
        const atts = event.attributes

        const span = spans.find((span) => span.events_json.some((s) => s.attributes?.id === atts.id))

        return (
          <div key={atts.id}>
            <div className={'flex gap-x-2 items-start'}>
              {/* <PlayIcon className={'size-5 text-orange-300'} /> */}

              <div className={'font-normal'}>
                <div className={'font-bold'}>{span?.name}</div>
                <div>
                  {atts['junjo.store.name']} &rarr; {atts['junjo.store.action']}
                </div>
                <div className={'opacity-50 text-xs'}>Patch: {atts.id}</div>
              </div>
            </div>
          </div>
        )
      })}
      <div className={'h-4'}></div>
    </div>
  )
}
