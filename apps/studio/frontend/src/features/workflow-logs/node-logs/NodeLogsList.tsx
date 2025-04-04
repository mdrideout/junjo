import { ForwardIcon } from '@heroicons/react/24/solid'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { NodeEventType, NodeSetStateEventSchema } from '../../otel/store/schemas'
import { selectSpanChildren } from '../../otel/store/selectors'
import RecursiveNodeChildSpans from './RecursiveNodeChildSpans'
import { Fragment } from 'react/jsx-runtime'
import { useMemo } from 'react'
import SpanSetStateEventsTR from './NodeSetStateEvents'
import NestedWorkflowSpans from './NestedWorkflowSpans'

interface NodeLogsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function NodeLogsList(props: NodeLogsListProps) {
  const { serviceName, workflowSpanID } = props

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
          {sortedSpans.map((span, index) => {
            // Get this span's set_state events
            const setStateEvents = span.events_json.filter((item) => item.name === NodeEventType.SET_STATE)

            // Make date human readable
            const start = new Date(span.start_time)
            const startString = start.toLocaleString()

            // Duration String
            const durationString = getSpanDurationString(span.start_time, span.end_time)
            return (
              <Fragment key={`${span.span_id}-tr-wrap-root`}>
                <tr
                  key={`${span.span_id}-table-index:${index}`}
                  className={`hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer`}
                  onClick={() => console.log('DO SOMETHING.')}
                >
                  <td className={'pl-2 py-1.5'}>{index + 1}</td>
                  <td className={'px-4 py-1.5'}>{span.name}</td>
                  <td className={'px-4 py-1.5'}>{span.span_id}</td>
                  <td className={'px-4 py-1.5'}>{startString}</td>
                  <td className={'pl-4 pr-2 py-1.5 text-right'}>{durationString}</td>
                </tr>
                <tr key={`${span.span_id}-children-index:${index}`}>
                  <td colSpan={5}>
                    {/* <RecursiveNodeChildSpans
                      key={`${span.span_id}-child-root`}
                      layer={0}
                      serviceName={serviceName}
                      workflowSpanID={span.span_id}
                    /> */}
                  </td>
                </tr>

                {/* <SpanSetStateEventsTR span={span} /> */}

                <tr
                  key={`${span.span_id}-border-index:${index}`}
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
