import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { selectSpanChildren } from '../../otel/store/selectors'
import { SpanIconConstructor } from './determine-span-icon'

interface RecursiveNodeChildSpansProps {
  layer: number
  serviceName: string
  workflowSpanID: string
}

/**
 * Recursive Node Child Spans
 * Recursively renders nested spans for the child spans
 * @param props
 * @returns
 */
export default function RecursiveNodeChildSpans(props: RecursiveNodeChildSpansProps) {
  const { layer, serviceName, workflowSpanID } = props

  const spans = useAppSelector((state: RootState) => selectSpanChildren(state, { serviceName, workflowSpanID }))
  const paddingLeft = layer + 1 * 32
  const isEven = layer % 2 === 0

  // Stop the recursion when there are no more children
  if (!spans || spans.length === 0) {
    return null
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
    <div style={{ paddingLeft: `${paddingLeft}px` }}>
      <div className={`${isEven ? '' : ''}`}>
        <table className={`text-left text-xs text-zinc-700 dark:text-zinc-200 w-full`}>
          {/* <thead>
            <tr>
              <th className={'px-2 pt-1'}>#</th>
              <th className={'px-4 pt-1'}>Name</th>
              <th className={'px-4 pt-1'}>Duration</th>
            </tr>
          </thead> */}
          <tbody>
            {sortedSpans.map((item, index) => {
              // Make date human readable
              const start = new Date(item.start_time)
              const startString = start.toLocaleString()

              // Duration String
              const durationString = getSpanDurationString(item.start_time, item.end_time)
              return (
                <>
                  <tr
                    key={`${item.span_id}-table-${layer}`}
                    className={'hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'}
                    onClick={() => console.log('TODO: Show attributes')}
                  >
                    <td className={'pl-2 py-1'}>
                      <SpanIconConstructor span={item} />
                    </td>
                    <td className={'px-2 py-1'}>{item.name}</td>
                    <td className={'px-2 py-1 text-right'}>{durationString}</td>
                  </tr>
                  <tr
                    key={`${item.span_id}-children-${layer}`}
                    className={'hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'}
                  >
                    <td colSpan={3}>
                      <RecursiveNodeChildSpans
                        layer={layer + 1}
                        serviceName={serviceName}
                        workflowSpanID={item.span_id}
                      />
                    </td>
                  </tr>
                  <tr
                    key={`${item.span_id}-border-${layer}`}
                    className={
                      'last-of-type:border-0 border-b border-zinc-400 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
                    }
                    onClick={() => console.log('DO SOMETHING.')}
                  >
                    <td colSpan={2}></td>
                  </tr>
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
