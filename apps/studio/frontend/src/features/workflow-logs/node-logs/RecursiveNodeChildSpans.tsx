import { Fragment } from 'react/jsx-runtime'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString, isoStringToMicrosecondsSinceEpoch } from '../../../util/duration-utils'
import { selectSpanChildren } from '../../otel/store/selectors'
import { SpanIconConstructor } from './determine-span-icon'
import { useMemo } from 'react'
import SpanSetStateEventsTR from './NodeSetStateEvents'
import {
  JunjoSpanType,
  NodeEventType,
  NodeSetStateEvent,
  NodeSetStateEventSchema,
  OtelSpan,
} from '../../otel/store/schemas'

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

  // Rows
  enum RowType {
    SPAN = 'SPAN',
    STATE = 'STATE',
  }

  interface SpanRow {
    type: RowType.SPAN
    data: OtelSpan
    time: number
  }

  interface StateRow {
    type: RowType.STATE
    data: NodeSetStateEvent
    time: number
  }

  type RowData = SpanRow | StateRow
  const rows: RowData[] = []

  // For each sortedSpan, add a row
  spans.forEach((span) => {
    // Get this span's children

    // Create the RowData and add it to rows
    rows.push({
      type: RowType.SPAN,
      data: span,
      time: isoStringToMicrosecondsSinceEpoch(span.end_time),
    })

    // Add the span's state event as a row
    const setStateEvents = span.events_json.filter((item) => item.name === NodeEventType.SET_STATE)

    setStateEvents.forEach((event) => {
      const validated = NodeSetStateEventSchema.safeParse(event)
      if (validated.error) {
        console.log('ERROR: ', validated.error)
        return <div className={'text-red-700'}>Invalid state update metadata.</div>
      }
      console.log('Adding state row: ', validated.data.name)
      rows.push({
        type: RowType.STATE,
        data: validated.data,
        time: validated.data.timeUnixNano,
      })
    })
  })

  // Sort the rows by time
  rows.sort((a, b) => a.time - b.time)

  console.log('ROWS: ', rows)

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
            {rows.map((row, index) => {
              return (
                <Fragment key={`${row.type}-${row.time}-${index}`}>
                  {row.type === RowType.SPAN && (
                    <>
                      <tr>
                        <td>SPAN</td>
                      </tr>
                    </>
                  )}
                  {row.type === RowType.STATE && (
                    <SpanSetStateEventsTR
                      span={
                        spans.find((s) =>
                          s.events_json.find((e) => e.attributes.id === row.data.attributes.id),
                        )!
                      }
                    />
                  )}
                </Fragment>
              )
            })}
            {/* {sortedSpans.map((span, index) => {
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
            })} */}
          </tbody>
        </table>
      </div>
    </div>
  )
}
