import { ForwardIcon } from '@heroicons/react/24/solid'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { NodeEventType, NodeSetStateEventSchema } from '../../otel/store/schemas'
import { selectSpanChildren } from '../../otel/store/selectors'
import RecursiveNodeChildSpans from './RecursiveNodeChildSpans'
import { useActiveNodeContext } from '../workflow-detail/ActiveNodeContext'
import { Fragment } from 'react/jsx-runtime'
import { useMemo } from 'react'

interface NodeLogsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function NodeLogsList(props: NodeLogsListProps) {
  const { serviceName, workflowSpanID } = props
  const { activeNodeSetStateEvent, setActiveNodeSetStateEvent } = useActiveNodeContext()

  // 1. Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  const spans = useAppSelector((state: RootState) => selectSpanChildren(state, selectorProps))

  if (!spans || spans.length === 0) {
    return <div>No node logs found for this workflow.</div>
  }

  // Order the spans from oldest to newest
  const sortedSpans = [...spans].sort((a, b) => {
    const aDate = new Date(a.start_time)
    const bDate = new Date(b.start_time)

    const aTime = aDate.getTime()
    const bTime = bDate.getTime()

    return aTime - bTime
  })

  return (
    <div>
      <table className="text-left text-sm">
        <thead>
          <tr>
            <th className={'pl-2 py-1'}>#</th>
            <th className={'px-4 py-1'}>Node Name</th>
            <th className={'px-4 py-1'}>Span ID</th>
            <th className={'px-4 py-1'}>Start Time</th>
            <th className={'pl-4 pr-2 py-1'}>Duration</th>
          </tr>
        </thead>
        <tbody>
          {sortedSpans.map((item, index) => {
            // Get this node's set_state events
            const setStateEvents = item.events_json.filter((item) => item.name === NodeEventType.SET_STATE)

            // Make date human readable
            const start = new Date(item.start_time)
            const startString = start.toLocaleString()

            // Duration String
            const durationString = getSpanDurationString(item.start_time, item.end_time)
            return (
              <Fragment key={`${item.span_id}-tr-wrap-root`}>
                <tr
                  key={`${item.span_id}-table-index:${index}`}
                  className={`hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer`}
                  onClick={() => console.log('DO SOMETHING.')}
                >
                  <td className={'pl-2 py-1.5'}>{index + 1}</td>
                  <td className={'px-4 py-1.5'}>{item.name}</td>
                  <td className={'px-4 py-1.5'}>{item.span_id}</td>
                  <td className={'px-4 py-1.5'}>{startString}</td>
                  <td className={'pl-4 pr-2 py-1.5 text-right'}>{durationString}</td>
                </tr>
                <tr key={`${item.span_id}-children-index:${index}`}>
                  <td colSpan={5}>
                    <RecursiveNodeChildSpans
                      key={`${item.span_id}-child-root`}
                      layer={0}
                      serviceName={serviceName}
                      workflowSpanID={item.span_id}
                    />
                  </td>
                </tr>

                {setStateEvents.length > 0 && (
                  <tr key={`${item.span_id}-set_state-index:${index}`}>
                    <td colSpan={5} className={'pl-[32px] text-xs pb-4'}>
                      {setStateEvents.map((event) => {
                        // Validate the event is a set state event
                        const validated = NodeSetStateEventSchema.safeParse(event)
                        if (validated.error) {
                          console.log('ERROR: ', validated.error)
                          return <div className={'text-red-700'}>Invalid state update metadata.</div>
                        }

                        const isActivePatch =
                          validated.data.attributes.id === activeNodeSetStateEvent?.attributes.id

                        return (
                          <div
                            key={`set-state-event-${validated.data.attributes.id}`}
                            className={`flex gap-x-1 py-1 pl-2 border-t border-zinc-200 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-amber-200 dark:hover:bg-amber-900 cursor-pointer ${isActivePatch ? 'bg-amber-100 dark:bg-amber-950' : ''}`}
                            onClick={() => {
                              setActiveNodeSetStateEvent(validated.data)
                            }}
                          >
                            <div>
                              <div className={'flex gap-x-0.5 font-bold'}>
                                <ForwardIcon className={'size-4 mr-1.5 text-orange-300'} />
                                <span className={'text-orange-300'}>STATE</span>
                                <div className={'font-normal'}>
                                  &rarr; {validated.data.attributes['junjo.store.name']} &rarr;{' '}
                                  {validated.data.attributes['junjo.store.action']}
                                </div>
                              </div>
                              <div className={'pl-6'}>Patch: {validated.data.attributes.id}</div>
                            </div>
                          </div>
                        )
                      })}
                    </td>
                  </tr>
                )}

                <tr
                  key={`${item.span_id}-border-index:${index}`}
                  className={
                    'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
                  }
                  onClick={() => console.log('DO SOMETHING.')}
                >
                  <td colSpan={5}></td>
                </tr>
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
