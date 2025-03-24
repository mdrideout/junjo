import { ForwardIcon } from '@heroicons/react/24/outline'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { NodeEventType, NodeSetStateEventSchema } from '../../otel/store/schemas'
import { selectSpanChildren } from '../../otel/store/selectors'
import RecursiveNodeChildSpans from './RecursiveNodeChildSpans'
import { ActiveStatePatch, useActiveNodeContext } from '../workflow-detail/ActiveNodeContext'

interface NodeLogsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function NodeLogsList(props: NodeLogsListProps) {
  const { serviceName, workflowSpanID } = props
  const { activeStatePatch, setActiveStatePatch } = useActiveNodeContext()

  const spans = useAppSelector((state: RootState) => selectSpanChildren(state, { serviceName, workflowSpanID }))

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
              <>
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
                    <RecursiveNodeChildSpans layer={0} serviceName={serviceName} workflowSpanID={item.span_id} />
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
                          validated.data.attributes.id === activeStatePatch?.patchID &&
                          item.span_id === activeStatePatch?.nodeSpanID

                        return (
                          <div
                            key={`set-state-event-${validated.data.attributes.id}`}
                            className={`flex gap-x-1 py-1 pl-2 border-t border-zinc-200 dark:border-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer ${isActivePatch ? 'bg-amber-100 dark:bg-amber-950' : ''}`}
                            onClick={() => {
                              const activePatch: ActiveStatePatch = {
                                nodeSpanID: item.span_id,
                                patchID: validated.data.attributes.id,
                              }
                              setActiveStatePatch(activePatch)
                            }}
                          >
                            <ForwardIcon className={'size-4 text-zinc-600 dark:text-zinc-400 mr-1.5'} />
                            STATE &rarr; {validated.data.attributes['junjo.store.name']} &rarr;{' '}
                            {validated.data.attributes['junjo.store.action']}
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
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
