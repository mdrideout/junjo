import type { JGraph, JNode } from '../junjo-graph/schemas'

export const JUNJO_GRAPH_NODE_ATTRIBUTE = 'data-junjo-graph-node-id'

function renderedElementMatchesNode(element: Element, node: JNode): boolean {
  const elementId = element.id
  const nodeId = node.nodeRuntimeId
  if (elementId === nodeId) return true

  if (element.classList.contains('node')) {
    return elementId.includes(`flowchart-${nodeId}-`)
  }

  if (element.classList.contains('cluster')) {
    return elementId.endsWith(`-${nodeId}`)
  }

  return false
}

/**
 * Establish Junjo-owned identity on Mermaid's renderer-owned DOM.
 *
 * Mermaid element IDs are deliberately not exposed to feature code. Matching
 * is constrained by the known node IDs in this exact Graph snapshot, and every
 * downstream interaction uses the Junjo data attribute and returned index.
 */
export function indexRenderedGraphElements(
  container: HTMLElement,
  graphSnapshot: JGraph,
): Map<string, Element> {
  const index = new Map<string, Element>()
  const graphNodesByLongestId = [...graphSnapshot.nodes].sort(
    (left, right) => right.nodeRuntimeId.length - left.nodeRuntimeId.length,
  )

  for (const element of container.querySelectorAll('.node, .cluster')) {
    element.removeAttribute(JUNJO_GRAPH_NODE_ATTRIBUTE)
    const node = graphNodesByLongestId.find((candidate) =>
      renderedElementMatchesNode(element, candidate),
    )
    if (node === undefined || index.has(node.nodeRuntimeId)) continue

    element.setAttribute(JUNJO_GRAPH_NODE_ATTRIBUTE, node.nodeRuntimeId)
    index.set(node.nodeRuntimeId, element)
  }

  return index
}

export function findIndexedGraphElementFromTarget(
  container: HTMLElement,
  target: EventTarget | null,
): Element | null {
  if (!(target instanceof Element)) return null
  const element = target.closest(`[${JUNJO_GRAPH_NODE_ATTRIBUTE}]`)
  return element !== null && container.contains(element) ? element : null
}
