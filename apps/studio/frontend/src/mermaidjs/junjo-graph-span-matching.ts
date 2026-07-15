import { OtelSpan } from '../features/traces/schemas/schemas'
import { wrapSpan } from '../features/traces/utils/span-accessor'
import { JGraph, JNode } from '../junjo-graph/schemas'

export function findGraphNodeByRenderedId(
  graphSnapshot: JGraph,
  renderedGraphNodeId: string,
): JNode | undefined {
  return graphSnapshot.nodes.find((node) => node.nodeRuntimeId === renderedGraphNodeId)
}

export function findSpanForRenderedGraphNodeId(
  graphSnapshot: JGraph,
  renderedGraphNodeId: string,
  spans: OtelSpan[],
): OtelSpan | undefined {
  const node = findGraphNodeByRenderedId(graphSnapshot, renderedGraphNodeId)
  if (!node) {
    return undefined
  }

  if (node.isSubflow) {
    return spans.find((span) => {
      const accessor = wrapSpan(span)
      if (!accessor.isSubflow) {
        return false
      }

      if (
        node.subflowGraphStructuralId &&
        accessor.executableStructuralId === node.subflowGraphStructuralId
      ) {
        return true
      }

      return accessor.executableDefinitionId === node.nodeRuntimeId
    })
  }

  return spans.find((span) => {
    const accessor = wrapSpan(span)
    if (!accessor.isNode && !accessor.isRunConcurrent) {
      return false
    }

    return accessor.executableRuntimeId === node.nodeRuntimeId
  })
}

export function findRenderedGraphNodeIdForSpan(
  graphSnapshot: JGraph,
  span: OtelSpan,
): string | null {
  const accessor = wrapSpan(span)

  if (accessor.isSubflow) {
    const subflowNode = graphSnapshot.nodes.find((node) => {
      if (!node.isSubflow) {
        return false
      }

      if (
        node.subflowGraphStructuralId &&
        accessor.executableStructuralId === node.subflowGraphStructuralId
      ) {
        return true
      }

      return accessor.executableDefinitionId === node.nodeRuntimeId
    })

    return subflowNode?.nodeRuntimeId ?? null
  }

  if (accessor.isNode || accessor.isRunConcurrent) {
    const runtimeId = accessor.executableRuntimeId
    if (!runtimeId) {
      return null
    }

    const hasNode = graphSnapshot.nodes.some((node) => node.nodeRuntimeId === runtimeId)
    return hasNode ? runtimeId : null
  }

  return null
}

/** Find the nearest physical ancestor represented in this exact Graph. */
export function findNearestSpanRepresentedInGraph(
  graphSnapshot: JGraph,
  selectedSpan: OtelSpan | null | undefined,
  traceSpans: OtelSpan[],
): OtelSpan | undefined {
  if (selectedSpan === null || selectedSpan === undefined) return undefined

  const spansById = new Map(traceSpans.map((span) => [span.span_id, span]))
  const visited = new Set<string>()
  let current: OtelSpan | undefined = spansById.get(selectedSpan.span_id) ?? selectedSpan

  while (current !== undefined && !visited.has(current.span_id)) {
    visited.add(current.span_id)
    if (findRenderedGraphNodeIdForSpan(graphSnapshot, current) !== null) {
      return current
    }
    current = current.parent_span_id === null
      ? undefined
      : spansById.get(current.parent_span_id)
  }

  return undefined
}
