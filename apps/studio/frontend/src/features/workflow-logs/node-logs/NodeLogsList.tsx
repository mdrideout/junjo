import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { selectWorkflowSpanChildren } from '../../otel/store/selectors'

interface NodeLogsListProps {
  serviceName: string
  workflowSpanID: string
}

export default function NodeLogsList(props: NodeLogsListProps) {
  const { serviceName, workflowSpanID } = props

  const spans = useAppSelector((state: RootState) => selectWorkflowSpanChildren(state, { serviceName, workflowSpanID }))

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
            <th className={'px-2 py-1'}>#</th>
            <th className={'px-4 py-1'}>Node Name</th>
            <th className={'px-4 py-1'}>Span ID</th>
            <th className={'px-4 py-1'}>Start Time</th>
            <th className={'px-4 py-1'}>Duration</th>
          </tr>
        </thead>
        <tbody>
          {sortedSpans.map((item, index) => {
            // Make date human readable
            const start = new Date(item.start_time)
            const startString = start.toLocaleString()

            // Duration String
            const durationString = getSpanDurationString(item.start_time, item.end_time)
            return (
              <tr
                key={item.span_id}
                className={
                  'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
                }
                onClick={() => console.log('DO SOMETHING.')}
              >
                <td className={'px-2 py-1.5'}>{index + 1}</td>
                <td className={'px-4 py-1.5'}>{item.name}</td>
                <td className={'px-4 py-1.5'}>{item.span_id}</td>
                <td className={'px-4 py-1.5'}>{startString}</td>
                <td className={'px-4 py-1.5 text-right'}>{durationString}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
