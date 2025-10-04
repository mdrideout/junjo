import { Fragment } from 'react/jsx-runtime'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import { isoStringToMicrosecondsSinceEpoch, nanoSecondsToMicrosecons } from '../../../util/duration-utils'
import { JSX, useEffect, useRef } from 'react'
import {
  JunjoSpanType,
  NodeEventType,
  JunjoSetStateEvent,
  JunjoSetStateEventSchema,
  OtelSpan,
} from '../../traces/schemas/schemas'
import { PlayIcon } from '@heroicons/react/24/solid'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'
import NestedSpanRow from './NestedSpanRow'
import { selectSpanAndChildren } from '../../traces/store/selectors'

interface NestedWorkflowSpansProps {
  traceId: string
  workflowSpanId: string
}

/**
 * Recursive Node Child Spans
 * Recursively renders nested spans for the child spans
 * @param props
 * @returns
 */
export default function NestedWorkflowSpans(props: NestedWorkflowSpansProps) {
  const { traceId, workflowSpanId } = props
  const dispatch = useAppDispatch()
  const scrollableContainerRef = useRef<HTMLDivElement>(null)

  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const scrollToSpanId = useAppSelector((state: RootState) => state.workflowDetailState.scrollToSpanId)
  const scrollToStateEventId = useAppSelector(
    (state: RootState) => state.workflowDetailState.scrollToStateEventId,
  )

  // Get the workflow span and its children
  const spans = useAppSelector((state: RootState) =>
    selectSpanAndChildren(state, {
      traceId,
      spanId: workflowSpanId,
    }),
  )

  // Sort the spans by start time
  spans.sort((a, b) => {
    const aTime = isoStringToMicrosecondsSinceEpoch(a.start_time)
    const bTime = isoStringToMicrosecondsSinceEpoch(b.start_time)

    return aTime - bTime
  })

  // Filter the spans to only include the top level spans
  const topLevelSpans = spans.filter((span) => span.parent_span_id === workflowSpanId)

  // Scroll To Span
  useEffect(() => {
    if (scrollToSpanId && scrollableContainerRef.current) {
      const targetSpanId = `#nested-span-${scrollToSpanId}`
      console.log(`Scrolling to span: ${targetSpanId}`)
      const targetElement = scrollableContainerRef.current.querySelector(targetSpanId)
      if (targetElement) {
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'nearest',
        })
      }
    }
  }, [scrollToSpanId])

  // Scroll To State Event
  useEffect(() => {
    if (scrollToStateEventId && scrollableContainerRef.current) {
      const targetStateEventId = `#nested-state-patch-${scrollToStateEventId}`
      const targetElement = scrollableContainerRef.current.querySelector(targetStateEventId)
      if (targetElement) {
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'nearest',
        })
      }
    }
  }, [scrollToStateEventId])

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
    data: JunjoSetStateEvent
    time: number
    parentSpan: OtelSpan
  }

  type RowData = SpanRow | StateRow
  const topLevelRows: RowData[] = []

  /**
   * Generate Rows
   * Recursive function to populate rows with the correct indentation / nesting
   * @param   function generateChildRows(parentSpan: OtelSpan[], layer: number) {

   * @param layer
   */
  function generateChildRows(parentSpan: OtelSpan, layer: number): RowData[] {
    const childRows: RowData[] = []

    // Get this span's state events and add them to the child rows
    const spanSetStateEvents = parentSpan.events_json.filter((item) => item.name === NodeEventType.SET_STATE)
    spanSetStateEvents.forEach((event) => {
      const validated = JunjoSetStateEventSchema.safeParse(event)
      if (validated.error) {
        console.log('ERROR: ', validated.error)
        return
      }
      childRows.push({
        type: RowType.STATE,
        data: validated.data,
        time: nanoSecondsToMicrosecons(validated.data.timeUnixNano),
        parentSpan: parentSpan,
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

  /**
   * Recursive Nested Row
   * Recursively renders the nested rows
   * @param param0
   * @returns
   */
  function RecursiveNestedRow({ row, layer }: { row: RowData; layer: number }): JSX.Element {
    /** Render Span Row **/
    if (row.type === RowType.SPAN) {
      const isActiveSpan = row.data.span_id === activeSpan?.span_id
      const spanTypeOther = row.data.junjo_span_type === JunjoSpanType.OTHER

      return (
        <Fragment key={`nested-span-${row.data.span_id}-${layer}`}>
          <div
            id={`nested-span-${row.data.span_id}`}
            className={`rounded-md ${!spanTypeOther ? 'pb-2 last-of-type:pb-0' : ''} ${layer > 0 ? 'ml-3 text-sm' : 'ml-0'} ${isActiveSpan ? 'bg-gradient-to-br from-zinc-100 dark:from-zinc-800 to-zinc-50 dark:to-zinc-900' : ''}`}
          >
            <NestedSpanRow span={row.data} isActiveSpan={isActiveSpan} />
            {row.childRows.length > 0 && (
              <div
                className={`border-l ml-[13px]  ${isActiveSpan ? 'border-amber-500' : 'border-zinc-300 dark:border-zinc-700'}`}
              >
                {row.childRows.map((childRow, index) => {
                  return (
                    <RecursiveNestedRow
                      key={`nested-row-${index}-${childRow.data.name}`}
                      row={childRow}
                      layer={layer + 1}
                    />
                  )
                })}
              </div>
            )}
          </div>
        </Fragment>
      )
    }

    /** Render State Row **/
    if (row.type === RowType.STATE) {
      const isActivePatch = row.data.attributes.id === activeSetStateEvent?.attributes.id

      return (
        <Fragment key={`state-${row.data.attributes.id}-${layer}`}>
          <div
            id={`nested-state-patch-${row.data.attributes.id}`}
            className={`p-1 cursor-pointer border-b last:border-0 border-zinc-200 dark:border-zinc-700 hover:bg-amber-200 dark:hover:bg-amber-900 ${layer > 0 ? 'ml-3 text-sm' : 'ml-0'} ${isActivePatch ? 'bg-amber-100 dark:bg-amber-950' : ''}`}
            onClick={() => {
              // Set the active span that this state event belongs to
              dispatch(WorkflowDetailStateActions.setActiveSpan(row.parentSpan))

              // Set the active set state event
              dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(row.data))
            }}
          >
            <div className={'flex gap-x-2 items-start'}>
              {layer > 0 && <PlayIcon className={'size-5 text-orange-300'} />}

              <div className={'font-normal'}>
                <div>
                  {row.data.attributes['junjo.store.name']} &rarr; {row.data.attributes['junjo.store.action']}
                </div>
                <div className={'opacity-50 text-xs'}>{row.data.attributes.id}</div>
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
    <div ref={scrollableContainerRef}>
      {topLevelRows.map((row) => {
        return (
          <Fragment key={`row-${row.time}`}>
            <RecursiveNestedRow row={row} layer={0} />
            <div className={'h-5'}></div>
          </Fragment>
        )
      })}
    </div>
  )
}
