import { Fragment } from 'react/jsx-runtime'
import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import {
  getSpanDurationString,
  isoStringToMicrosecondsSinceEpoch,
  nanoSecondsToMicrosecons,
} from '../../../util/duration-utils'
import { selectAllWorkflowChildSpans, selectSpanChildren } from '../../otel/store/selectors'
import { SpanIconConstructor } from './determine-span-icon'
import { JSX, useMemo } from 'react'
import SpanSetStateEventsTR from './NodeSetStateEvents'
import {
  JunjoSpanType,
  NodeEventType,
  NodeSetStateEvent,
  NodeSetStateEventSchema,
  OtelSpan,
} from '../../otel/store/schemas'
import { ForwardIcon } from '@heroicons/react/16/solid'
import { useActiveNodeContext } from '../workflow-detail/ActiveNodeContext'

interface NestedWorkflowSpansProps {
  serviceName: string
  workflowSpanID: string
}

/**
 * Recursive Node Child Spans
 * Recursively renders nested spans for the child spans
 * @param props
 * @returns
 */
export default function NestedWorkflowSpans(props: NestedWorkflowSpansProps) {
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

  // 2. Use the memoized props object in useAppSelector
  const spans = useAppSelector((state: RootState) => selectAllWorkflowChildSpans(state, selectorProps))
  // Sort the spans by start time
  spans.sort((a, b) => {
    const aTime = isoStringToMicrosecondsSinceEpoch(a.start_time)
    const bTime = isoStringToMicrosecondsSinceEpoch(b.start_time)

    return aTime - bTime
  })

  // Filter the spans to only include the top level spans

  const topLevelSpans = spans.filter((span) => span.parent_span_id === workflowSpanID)
  console.log('Top level spans: ', topLevelSpans)

  // Stop the recursion when there are no more children
  if (!spans || spans.length === 0) {
    return <div>No data available for this workflow.</div>
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
    childRows: RowData[]
  }

  interface StateRow {
    type: RowType.STATE
    data: NodeSetStateEvent
    time: number
  }

  type RowData = SpanRow | StateRow
  const topLevelRows: RowData[] = []

  // TODO
  // For each span
  // Generate a row
  // Recursively generate nested rows for its children
  // LEFT OFF HERE

  /**
   * Generate Rows
   * Recursive function to populate rows with the correct indentation / nesting
   * @param   function generateChildRows(parentSpan: OtelSpan[], layer: number) {

   * @param layer
   */
  function generateChildRows(parentSpan: OtelSpan, layer: number): RowData[] {
    const childRows: RowData[] = []

    // Get this span's state events and add them to the child rows
    const setStateEvents = parentSpan.events_json.filter((item) => item.name === NodeEventType.SET_STATE)
    setStateEvents.forEach((event) => {
      const validated = NodeSetStateEventSchema.safeParse(event)
      if (validated.error) {
        console.log('ERROR: ', validated.error)
        return
      }
      childRows.push({
        type: RowType.STATE,
        data: validated.data,
        time: nanoSecondsToMicrosecons(validated.data.timeUnixNano),
      })
    })

    // Get this span's children
    const childSpans = spans.filter((span) => span.parent_span_id === parentSpan.span_id)
    // For each child span, add a row, then recursively generate its children
    childSpans.forEach((childSpan) => {
      const childRow: SpanRow = {
        type: RowType.SPAN,
        data: childSpan,
        time: isoStringToMicrosecondsSinceEpoch(childSpan.start_time),
        childRows: generateChildRows(childSpan, layer + 1),
      }
      childRows.push(childRow)
    })

    // Sort the childRows
    childRows.sort((a, b) => a.time - b.time)

    // Add the child rows to the main rows
    return childRows
  }

  // For each top level span, create a row, then generate its child rows
  for (const span of topLevelSpans) {
    topLevelRows.push({
      type: RowType.SPAN,
      data: span,
      time: isoStringToMicrosecondsSinceEpoch(span.start_time),
      childRows: generateChildRows(span, 1),
    })
  }

  // generateChildRows(spans, 0)

  console.log('ROWS: ', topLevelRows)

  /**
   * Recursive Nested Row
   * Recursively renders the nested rows
   * @param param0
   * @returns
   */
  function RecursiveNestedRow({ row, layer }: { row: RowData; layer: number }): JSX.Element {
    const marginLeft = layer * 24

    if (row.type === RowType.SPAN) {
      const nonWorkflowNodeSpan = row.data.junjo_span_type === JunjoSpanType.OTHER

      return (
        <Fragment key={`span-${row.data.span_id}-${layer}`}>
          <div className={`w-full ${layer > 0 ? 'ml-5 text-sm' : 'ml-0'}`}>
            <div
              className={`w-full p-1.5 ${nonWorkflowNodeSpan ? 'border-b border-zinc-300 dark:border-zinc-700' : ''}`}
            >
              <div className={`flex items-center gap-x-2`}>
                <SpanIconConstructor span={row.data} />
                <div>{row.data.name}</div>
              </div>
            </div>
            {row.childRows.length > 0 && (
              <div className={'w-full border-l ml-[15px] border-zinc-300 dark:border-zinc-700'}>
                {row.childRows.map((childRow) => {
                  return <RecursiveNestedRow row={childRow} layer={layer + 1} />
                })}
              </div>
            )}
          </div>
          {(layer === 0 || !nonWorkflowNodeSpan) && <div className={'h-5'}>&nbsp;</div>}
        </Fragment>
      )
    }

    if (row.type === RowType.STATE) {
      const isActivePatch = row.data.attributes.id === activeNodeSetStateEvent?.attributes.id

      return (
        <Fragment key={`state-${row.data.attributes.id}-${layer}`}>
          <div
            className={`w-full p-1.5 cursor-pointer border-b last:border-0 border-zinc-300 dark:border-zinc-700 hover:bg-amber-200 dark:hover:bg-amber-900 ${layer > 0 ? 'ml-5 text-sm' : 'ml-0'} ${isActivePatch ? 'bg-amber-100 dark:bg-amber-950' : ''}`}
            onClick={() => {
              setActiveNodeSetStateEvent(row.data)
            }}
          >
            <div className={'flex gap-x-2 items-start'}>
              {layer > 0 && <ForwardIcon className={'size-5 text-orange-300'} />}

              <div className={'font-normal'}>
                <div>
                  {row.data.attributes['junjo.store.name']} &rarr; {row.data.attributes['junjo.store.action']}
                </div>
                <div className={'opacity-50 text-xs'}>Patch: {row.data.attributes.id}</div>
              </div>
            </div>
          </div>
        </Fragment>
      )
    }

    return <></>
  }

  // Sort the top level rows by time
  topLevelRows.sort((a, b) => a.time - b.time)

  return (
    <div className={'grow'}>
      {topLevelRows.map((row) => {
        return (
          <Fragment key={`row-${row.time}`}>
            <RecursiveNestedRow row={row} layer={0} />
          </Fragment>
        )
      })}
    </div>
  )
}
