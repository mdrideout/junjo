import { JunjoGraphError } from './errors'
import { JEdge, JGraph, JGraphSchema, JNode } from './schemas'
import { escapeMermaidLabel, MermaidGraphDirection } from './utils'

export class JunjoGraph {
  private graph: JGraph

  private constructor(graph: JGraph) {
    this.graph = graph
  }

  static fromJson(json: unknown): JunjoGraph {
    const parsed = JGraphSchema.safeParse(json)
    if (!parsed.success) {
      const errorMessage = `Invalid execution graph snapshot: ${JSON.stringify(parsed.error.issues)}`
      throw new JunjoGraphError(errorMessage)
    }

    return new JunjoGraph(parsed.data)
  }

  get nodes(): JNode[] {
    return this.graph.nodes
  }

  get edges(): JEdge[] {
    return this.graph.edges
  }

  get version(): number {
    return this.graph.v
  }

  get graphStructuralId(): string {
    return this.graph.graphStructuralId
  }

  toMermaid(
    showEdgeLabels: boolean = false,
    direction: MermaidGraphDirection = 'LR',
    subDirection: MermaidGraphDirection = 'LR',
  ): string {
    const lines: string[] = []
    const nodeMap = new Map<string, JNode>(this.graph.nodes.map((node) => [node.nodeRuntimeId, node]))
    const concurrentChildIds = new Set<string>()
    const concurrentContainerIds = new Set<string>()
    const subflowInternalNodeIds = new Set<string>()

    for (const node of this.graph.nodes) {
      if (node.isConcurrentSubgraph) {
        concurrentContainerIds.add(node.nodeRuntimeId)
        for (const childNodeRuntimeId of node.childNodeRuntimeIds ?? []) {
          concurrentChildIds.add(childNodeRuntimeId)
        }
      }

      if (node.isSubflow) {
        if (node.subflowSourceNodeRuntimeId) {
          subflowInternalNodeIds.add(node.subflowSourceNodeRuntimeId)
        }

        for (const sinkNodeRuntimeId of node.subflowSinkNodeRuntimeIds ?? []) {
          subflowInternalNodeIds.add(sinkNodeRuntimeId)
        }
      }
    }

    for (const edge of this.graph.edges) {
      if (edge.edgeScope !== 'subflow') {
        continue
      }
      subflowInternalNodeIds.add(edge.tailNodeRuntimeId)
      subflowInternalNodeIds.add(edge.headNodeRuntimeId)
    }

    lines.push(`graph ${direction}`)

    for (const node of this.graph.nodes) {
      const isConcurrentChild = concurrentChildIds.has(node.nodeRuntimeId)
      const isSubflowInternal = subflowInternalNodeIds.has(node.nodeRuntimeId)
      const isConcurrentContainer = concurrentContainerIds.has(node.nodeRuntimeId)

      if (isConcurrentChild || isSubflowInternal || isConcurrentContainer) {
        continue
      }

      const label = escapeMermaidLabel(node.nodeLabel)
      if (node.isSubflow) {
        lines.push(`  ${node.nodeRuntimeId}@{ shape: st-rect, label: ${label} }`)
      } else {
        lines.push(`  ${node.nodeRuntimeId}@{ shape: rect, label: ${label} }`)
      }
    }

    for (const node of this.graph.nodes) {
      if (!node.isConcurrentSubgraph) {
        continue
      }

      if (subflowInternalNodeIds.has(node.nodeRuntimeId)) {
        continue
      }

      lines.push('')
      lines.push(`  subgraph ${node.nodeRuntimeId} [${escapeMermaidLabel(node.nodeLabel)}]`)
      lines.push(`    direction ${subDirection}`)

      for (const childNodeRuntimeId of node.childNodeRuntimeIds ?? []) {
        const childNode = nodeMap.get(childNodeRuntimeId)
        if (!childNode || subflowInternalNodeIds.has(childNodeRuntimeId)) {
          continue
        }

        const childLabel = escapeMermaidLabel(childNode.nodeLabel)
        if (childNode.isSubflow) {
          lines.push(`    ${childNode.nodeRuntimeId}@{ shape: st-rect, label: ${childLabel} }`)
        } else {
          lines.push(`    ${childNode.nodeRuntimeId}@{ shape: rect, label: ${childLabel} }`)
        }
      }

      lines.push('  end')
    }

    lines.push('')
    for (const edge of this.graph.edges) {
      if (edge.edgeScope === 'subflow') {
        continue
      }

      if (
        subflowInternalNodeIds.has(edge.tailNodeRuntimeId) ||
        subflowInternalNodeIds.has(edge.headNodeRuntimeId)
      ) {
        continue
      }

      if (!nodeMap.has(edge.tailNodeRuntimeId) || !nodeMap.has(edge.headNodeRuntimeId)) {
        continue
      }

      const condition = edge.edgeConditionLabel ? escapeMermaidLabel(edge.edgeConditionLabel) : null
      if (condition && showEdgeLabels) {
        lines.push(`  ${edge.tailNodeRuntimeId} -.${condition}.-> ${edge.headNodeRuntimeId}`)
      } else if (condition) {
        lines.push(`  ${edge.tailNodeRuntimeId} -.-> ${edge.headNodeRuntimeId}`)
      } else {
        lines.push(`  ${edge.tailNodeRuntimeId} --> ${edge.headNodeRuntimeId}`)
      }
    }

    return lines.join('\n')
  }
}
