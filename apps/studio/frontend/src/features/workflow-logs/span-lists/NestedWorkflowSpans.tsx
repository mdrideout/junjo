import { Fragment } from 'react/jsx-runtime'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import {
  getSpanDurationString,
  isoStringToMicrosecondsSinceEpoch,
  nanoSecondsToMicrosecons,
} from '../../../util/duration-utils'
import { selectAllWorkflowChildSpans } from '../../otel/store/selectors'
import { SpanIconConstructor } from './determine-span-icon'
import { JSX, useEffect, useMemo, useRef } from 'react'
import {
  JunjoSpanType,
  NodeEventType,
  JunjoSetStateEvent,
  JunjoSetStateEventSchema,
  OtelSpan,
} from '../../otel/store/schemas'
import { PlayIcon } from '@heroicons/react/24/solid'
import { WorkflowDetailStateActions } from '../workflow-detail/store/slice'

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

  // Scroll To Span
  useEffect(() => {
    if (scrollToSpanId && scrollableContainerRef.current) {
      const targetSpanId = `#span-${scrollToSpanId}`
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
      const targetStateEventId = `#state-patch-${scrollToStateEventId}`
      console.log(`Scrolling to state event: ${targetStateEventId}`)
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
      const nonWorkflowNodeSpan = row.data.junjo_span_type === JunjoSpanType.OTHER
      const start_time = row.data.start_time
      const end_time = row.data.end_time
      const spanDuration = getSpanDurationString(start_time, end_time)

      const isActiveSpan = row.data.span_id === activeSpan?.span_id

      return (
        <Fragment key={`span-${row.data.span_id}-${layer}`}>
          <div
            id={`span-${row.data.span_id}`}
            className={`rounded-md ${!nonWorkflowNodeSpan ? 'pb-2 last-of-type:pb-0' : ''} ${layer > 0 ? 'ml-3 text-sm' : 'ml-0'} ${isActiveSpan ? 'bg-gradient-to-br from-zinc-100 dark:from-zinc-800 to-zinc-50 dark:to-zinc-900 cursor-pointer' : ''}`}
          >
            <div
              className={`p-1 ${nonWorkflowNodeSpan ? 'border-b border-zinc-200 dark:border-zinc-700' : ''}`}
            >
              <div className={`flex gap-x-2 ${nonWorkflowNodeSpan ? 'items-start' : 'items-center'}`}>
                <SpanIconConstructor span={row.data} active={isActiveSpan} />
                <div className={'w-full flex gap-x-2 justify-between items-end'}>
                  <div>{row.data.name}</div>

                  <div className={'font-mono text-zinc-500 text-xs'}>{spanDuration}</div>
                </div>
              </div>
            </div>
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
            id={`state-patch-${row.data.attributes.id}`}
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
    <div ref={scrollableContainerRef}>
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
