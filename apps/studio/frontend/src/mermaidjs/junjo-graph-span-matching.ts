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
