import { JunjoGraphError } from './errors'
import { JEdge, JGraph, JGraphSchema, JNode } from './schemas'
import { escapeMermaidLabel, MermaidGraphDirection } from './utils'

export class JunjoGraph {
  private graph: JGraph

  private constructor(graph: JGraph) {
    this.graph = graph
  }

  /**
   * Factory Constructor: From Base64 JSON
   *
   * The Junjo server stores graph structures as JSONB in the SQLite database.
   * It is returned to the frontend as a Base64 encoded JSON string by default.
   *
   * This constructor creates an instance of JunjoGraph by
   * - Decoding the Base64 string
   * - Parsing the JSON
   * - Parsing the JGraph schema
   *
   * @param base64String is the raw Base64 encoded JSON string of the graph
   * @throws if there are any issues parsing the data
   * @returns an instance of JunjoGraph
   */
  static fromJson(json: Record<string, any>): JunjoGraph {
    try {
      const parsedData = JGraphSchema.safeParse(json)

      if (!parsedData.success) {
        const errorMessage = `Invalid JSON data or data structure: ${JSON.stringify(parsedData.error.issues)}.`
        console.error('Error parsing base64 encoded JSON:', errorMessage)
        throw new JunjoGraphError(errorMessage)
      }

      return new JunjoGraph(parsedData.data)
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      console.error('Error creating JunjoGraph:', message)
      throw new JunjoGraphError(`Failed to create JunjoGraph from base64 data: ${message}`)
    }
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

  /**
   * Convert the graph to a Mermaid flow‑chart definition.
   * @param showEdgeLabels – include edge conditions when true.
   * @param direction – overall graph direction, defaults to LR.
   * @param subDirection – direction to use inside RunConcurrent sub‑graphs, defaults to LR.
   */
  toMermaid(
    showEdgeLabels: boolean = false,
    direction: MermaidGraphDirection = 'LR',
    subDirection: MermaidGraphDirection = 'LR',
  ): string {
    const lines: string[] = []

    // ---------- 0. Prepared lookup sets ----------
    const nodeMap = new Map<string, JNode>(this.graph.nodes.map((n) => [n.id, n]))
    const childrenNodeIds = new Set<string>()
    const subgraphContainerIds = new Set<string>()
    const subflowNodeIds = new Set<string>()
    const subflowInternalNodeIds = new Set<string>()

    // ---------- 1. Pass: classify nodes ----------
    for (const node of this.graph.nodes) {
      if (node.isSubgraph && node.children?.length) {
        subgraphContainerIds.add(node.id)
        for (const ch of node.children) {
          childrenNodeIds.add(ch)
        }
      } else if (node.isSubflow) {
        subflowNodeIds.add(node.id)
        for (const e of this.graph.edges.filter((e) => e.subflowId === node.id)) {
          subflowInternalNodeIds.add(e.source)
          subflowInternalNodeIds.add(e.target)
        }
      }
    }

    // ---------- 2. Start diagram ----------
    lines.push(`graph ${direction}`)

    // ---------- 3. Top‑level nodes ----------
    for (const node of this.graph.nodes) {
      if (subflowInternalNodeIds.has(node.id)) continue // internal to a sub‑flow
      if (childrenNodeIds.has(node.id)) continue // rendered in subgraph
      if (subgraphContainerIds.has(node.id)) continue // container itself handled below

      const label = escapeMermaidLabel(node.label)
      if (subflowNodeIds.has(node.id)) {
        lines.push(`  ${node.id}@{ shape: st-rect, label: ${label} }`)
      } else {
        lines.push(`  ${node.id}@{ shape: rect, label: ${label} }`)
      }
    }

    // ---------- 4. RunConcurrent sub‑graphs ----------
    for (const node of this.graph.nodes) {
      if (!subgraphContainerIds.has(node.id)) continue
      if (subflowInternalNodeIds.has(node.id)) continue // NEW ➜ skip if this gather lives inside a sub‑flow

      lines.push('')
      lines.push(`  subgraph ${node.id} [${escapeMermaidLabel(node.label)}]`)
      lines.push(`    direction ${subDirection}`)

      for (const childId of node.children || []) {
        if (subflowInternalNodeIds.has(childId)) continue // child also internal
        const child = nodeMap.get(childId)
        if (!child) continue
        const lbl = escapeMermaidLabel(child.label)
        if (subflowNodeIds.has(child.id)) {
          lines.push(`    ${child.id}@{ shape: st-rect, label: ${lbl} }`)
        } else {
          lines.push(`    ${child.id}[${lbl}]`)
        }
      }

      lines.push('  end')
    }

    // ---------- 5. Edges ----------
    lines.push('')
    for (const edge of this.graph.edges) {
      if (edge.type === 'subflow') continue // hide internal edges
      if (subflowInternalNodeIds.has(edge.source) || subflowInternalNodeIds.has(edge.target)) continue
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) continue

      const src = edge.source
      const tgt = edge.target
      const cond = edge.condition ? escapeMermaidLabel(edge.condition) : null
      if (cond && showEdgeLabels) {
        lines.push(`  ${src} -.${cond}.-> ${tgt}`)
      } else if (cond) {
        lines.push(`  ${src} -.-> ${tgt}`)
      } else {
        lines.push(`  ${src} --> ${tgt}`)
      }
    }

    return lines.join('\n')
  }
}
