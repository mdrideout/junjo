import { ForwardIcon } from '@heroicons/react/16/solid'
import { NodeEventType, NodeSetStateEventSchema, OtelSpan } from '../../otel/store/schemas'
import { useActiveNodeContext } from '../workflow-detail/ActiveNodeContext'

interface SpanSetStateEventProps {
  span: OtelSpan
}

export default function SpanSetStateEventsTR(props: SpanSetStateEventProps) {
  const { span } = props
  const { activeNodeSetStateEvent, setActiveNodeSetStateEvent } = useActiveNodeContext()

  // Get this span's set_state events
  const setStateEvents = span.events_json.filter((item) => item.name === NodeEventType.SET_STATE)
  console.log('Set state events:', setStateEvents)

  return (
    <>
      {setStateEvents.length > 0 && (
        <tr key={`${span.span_id}-set_state-root`}>
          <td colSpan={5} className={'pl-[32px] text-xs pb-4'}>
            {setStateEvents.map((event) => {
              // Validate the event is a set state event
              const validated = NodeSetStateEventSchema.safeParse(event)
              if (validated.error) {
                console.log('ERROR: ', validated.error)
                return <div className={'text-red-700'}>Invalid state update metadata.</div>
              }

              const isActivePatch = validated.data.attributes.id === activeNodeSetStateEvent?.attributes.id

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
                    <div className={'pl-6 opacity-50'}>Patch: {validated.data.attributes.id}</div>
                  </div>
                </div>
              )
            })}
          </td>
        </tr>
      )}
    </>
  )
}
