import { Fragment } from 'react/jsx-runtime'
import { isoStringToMicrosecondsSinceEpoch } from '../../util/duration-utils'
import { OtelSpan } from '../otel/schemas/schemas'
import { JSX, useMemo } from 'react'
import SpanRow from './SpanRow'

interface NestedOtelSpansProps {
  spans: OtelSpan[]
  traceId: string
  selectedSpanId: string | null
  onSelectSpan: (span: OtelSpan) => void
}

export default function NestedOtelSpans(props: NestedOtelSpansProps) {
  const { spans, traceId, selectedSpanId, onSelectSpan } = props

  // Find the root span (the one with matching traceId as spanId or null parent)
  const rootSpan =
    spans.find((span) => span.span_id === traceId) ||
    spans.find((span) => span.parent_span_id === null || span.parent_span_id === '') ||
    spans[0] // fallback to first span

  // Get all spans except the root to use for nesting
  const childSpans = spans.filter((span) => span.span_id !== rootSpan?.span_id)

  // Stop if there are no spans
  if (!spans || spans.length === 0) {
    return <div>No spans available for this trace.</div>
  }

  interface SpanRowData {
    span: OtelSpan
    time: number
    childRows: SpanRowData[]
  }

  /**
   * Generate Rows
   * Recursive function to populate rows with the correct indentation / nesting
   */
  function generateChildRows(parentSpanId: string, layer: number): SpanRowData[] {
    const childRows: SpanRowData[] = []

    // Get this span's children
    const directChildren = childSpans.filter((span) => span.parent_span_id === parentSpanId)

    // For each child span, add a row, then recursively generate its children
    directChildren.forEach((childSpan) => {
      const childRow: SpanRowData = {
        span: childSpan,
        time: isoStringToMicrosecondsSinceEpoch(childSpan.start_time),
        childRows: generateChildRows(childSpan.span_id, layer + 1),
      }
      childRows.push(childRow)
    })

    // Sort the childRows by time
    childRows.sort((a, b) => a.time - b.time)

    return childRows
  }

  /**
   * Recursive Nested Row
   * Recursively renders the nested rows
   */
  function RecursiveNestedRow({ rowData, layer }: { rowData: SpanRowData; layer: number }): JSX.Element {
    const isActiveSpan = selectedSpanId === rowData.span.span_id
    const hasChildren = rowData.childRows.length > 0

    return (
      <Fragment key={`nested-span-${rowData.span.span_id}-${layer}`}>
        <div
          id={`nested-span-${rowData.span.span_id}`}
          className={`rounded-md ${hasChildren ? 'mb-2' : 'mb-0'} last-of-type:mb-0 ${layer > 0 ? 'ml-3 text-sm' : 'ml-0'}`}
        >
          <SpanRow span={rowData.span} isActiveSpan={isActiveSpan} onClick={onSelectSpan} />
          {hasChildren && (
            <div
              className={`border-l ml-[13px] ${isActiveSpan ? 'border-amber-500' : 'border-zinc-300 dark:border-zinc-700'}`}
            >
              {rowData.childRows.map((childRow, index) => {
                return (
                  <RecursiveNestedRow
                    key={`nested-row-${index}-${childRow.span.span_id}`}
                    rowData={childRow}
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

  // Generate rows starting from the root span
  const rootRowData: SpanRowData = {
    span: rootSpan!,
    time: isoStringToMicrosecondsSinceEpoch(rootSpan!.start_time),
    childRows: generateChildRows(rootSpan!.span_id, 0),
  }

  // Sort child rows by time
  rootRowData.childRows.sort((a, b) => a.time - b.time)

  return (
    <div>
      {/* Root span */}
      <div className="rounded-md pb-2">
        <SpanRow
          span={rootRowData.span}
          isActiveSpan={selectedSpanId === rootRowData.span.span_id}
          onClick={onSelectSpan}
        />
        {rootRowData.childRows.length > 0 && (
          <div className="border-l ml-[13px] border-zinc-300 dark:border-zinc-700">
            {rootRowData.childRows.map((childRow, index) => {
              return (
                <RecursiveNestedRow
                  key={`root-nested-row-${index}-${childRow.span.span_id}`}
                  rowData={childRow}
                  layer={1}
                />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
