import { Fragment } from 'react/jsx-runtime'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import { selectSpanChildren } from '../../otel/store/selectors'
import { SpanIconConstructor } from './determine-span-icon'
import { useMemo } from 'react'
import SpanSetStateEventsTR from './NodeSetStateEvents'
import { JunjoSpanType } from '../../otel/store/schemas'

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

  // 1. Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  // 2. Use the memoized props object in useAppSelector
  const spans = useAppSelector((state: RootState) => selectSpanChildren(state, selectorProps))
  const marginLeft = layer + 1 * 24
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
    <div style={{ marginLeft: `${marginLeft}px` }}>
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
            {sortedSpans.map((span, index) => {
              // Workflow / Node spans
              const isWorkflowOrNode =
                span.junjo_span_type === JunjoSpanType.NODE || span.junjo_span_type === JunjoSpanType.WORKFLOW

              // Make date human readable
              const start = new Date(span.start_time)
              const startString = start.toLocaleString()

              // Duration String
              const durationString = getSpanDurationString(span.start_time, span.end_time)
              return (
                <Fragment key={`${span.span_id}-tr-wrap-${layer}`}>
                  <tr
                    key={`${span.span_id}-table-${layer}-${index}`}
                    className={`${isWorkflowOrNode ? 'text-sm' : ''}`}
                    onClick={() => console.log('TODO: Show attributes')}
                  >
                    <td className={'pl-2 py-1 w-6'}>
                      <SpanIconConstructor span={span} />
                    </td>
                    <td className={'px-2 py-1'}>{span.name}</td>
                    <td className={'px-2 py-1 text-right'}>{durationString}</td>
                  </tr>

                  <tr
                    key={`${span.span_id}-children-${layer}`}
                    className={'hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'}
                  >
                    <td colSpan={3}>
                      <RecursiveNodeChildSpans
                        key={`${span.span_id}-child-td-${layer}-${index}`}
                        layer={layer + 1}
                        serviceName={serviceName}
                        workflowSpanID={span.span_id}
                      />
                    </td>
                  </tr>
                  <SpanSetStateEventsTR span={span} />
                  <tr
                    key={`${span.span_id}-border-${layer}`}
                    className={
                      'last-of-type:border-0 border-b border-zinc-400 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
                    }
                    onClick={() => console.log('DO SOMETHING.')}
                  >
                    <td colSpan={2}></td>
                  </tr>
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
