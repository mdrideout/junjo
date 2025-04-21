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
    console.log('Junjo Graph Raw JSON: ', json)

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
   * To Mermaid Flowchart
   *
   * Converts the Junjo Graph representation into a Mermaid flowchart definition string,
   * rendering nodes marked as subgraphs correctly and subflows as single nodes.
   *
   * @param {boolean} [showEdgeLabels=false] - If true, edge labels (conditions) will be included in the output.
   * @param {MermaidGraphDirection} direction - The overall direction of the flowchart. Defaults to 'LR'.
   * @param {MermaidGraphDirection} subDirection - Optional direction for layout within subgraphs. Defaults to 'LR'.
   * @returns {string} A string containing the Mermaid flowchart definition.
   */
  toMermaid(
    showEdgeLabels: boolean = false,
    direction: MermaidGraphDirection = 'LR',
    subDirection: MermaidGraphDirection = 'LR', // Default direction inside subgraphs
  ): string {
    const lines: string[] = []

    // Create a map for easy node lookup by ID
    const nodeMap = new Map<string, JNode>(this.graph.nodes.map((node) => [node.id, node]))

    // Sets to keep track of node roles
    const childrenNodeIds = new Set<string>() // Children of NodeGather
    const subgraphContainerIds = new Set<string>() // NodeGather containers
    const subflowNodeIds = new Set<string>() // Subflow nodes themselves
    const subflowInternalNodeIds = new Set<string>() // Nodes inside subflows (to be hidden)

    // 1. Preprocessing: Identify subgraph containers, subflows, and their children
    this.graph.nodes.forEach((node) => {
      if (node.isSubgraph && node.children && node.children.length > 0) {
        // Handle NodeGather subgraphs
        subgraphContainerIds.add(node.id)
        node.children.forEach((childId) => {
          if (nodeMap.has(childId)) {
            childrenNodeIds.add(childId)
          } else {
            console.warn(
              `Subgraph ${node.id} ('${node.label}') lists child ID ${childId}, but this node was not found.`,
            )
          }
        })
      } else if (node.isSubflow) {
        // Mark nodes that are subflows
        subflowNodeIds.add(node.id)

        // Find internal nodes of this subflow
        this.graph.edges
          .filter((edge) => edge.subflowId === node.id)
          .forEach((edge) => {
            // Both source and target are internal to the subflow
            subflowInternalNodeIds.add(edge.source)
            subflowInternalNodeIds.add(edge.target)
          })
      }
    })

    // 2. Start graph definition
    lines.push(`graph ${direction}`)

    // 3. Define top-level nodes, excluding subflow internals
    this.graph.nodes.forEach((node) => {
      // Skip if node is internal to a subflow
      if (subflowInternalNodeIds.has(node.id)) {
        return
      }

      // Skip if node is a child of a NodeGather (will be rendered within the subgraph)
      if (childrenNodeIds.has(node.id)) {
        return
      }

      // Skip if node is a NodeGather container (will be rendered as a subgraph)
      if (subgraphContainerIds.has(node.id)) {
        return
      }

      // For subflow nodes, use a different shape (cylindrical)
      if (subflowNodeIds.has(node.id)) {
        lines.push(`  ${node.id}@{ shape: st-rect, label: ${escapeMermaidLabel(node.label)} }`)
      } else {
        lines.push(`  ${node.id}@{ shape: rect, label: ${escapeMermaidLabel(node.label)} }`)
      }
    })

    // 4. Define subgraphs (NodeGather instances) and their children nodes
    this.graph.nodes.forEach((node) => {
      if (subgraphContainerIds.has(node.id)) {
        lines.push(``) // Add empty line for readability
        lines.push(`  subgraph ${node.id} [${escapeMermaidLabel(node.label)}]`)
        lines.push(`    direction ${subDirection}`) // Set internal direction

        node.children?.forEach((childId) => {
          const childNode = nodeMap.get(childId)
          if (childNode) {
            // Conditionally apply shape based on whether the child is a subflow node
            if (subflowNodeIds.has(childNode.id)) {
              lines.push(
                `    ${childNode.id}@{ shape: st-rect, label: ${escapeMermaidLabel(childNode.label)} }`,
              )
            } else {
              lines.push(`    ${childNode.id}[${escapeMermaidLabel(childNode.label)}]`)
            }
          }
        })
        lines.push(`  end`)
      }
    })

    // 5. Define all explicit edges, excluding subflow internal edges
    lines.push(``) // Add empty line for readability
    this.graph.edges.forEach((edge) => {
      // Skip subflow internal edges
      if (edge.type === 'subflow') {
        return
      }

      // Skip edges involving subflow internal nodes
      if (subflowInternalNodeIds.has(edge.source) || subflowInternalNodeIds.has(edge.target)) {
        return
      }

      // Basic validation: Ensure source and target nodes are valid
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) {
        console.warn(
          `Skipping edge '${edge.id}' because source ('${edge.source}') or target ('${edge.target}') node was not found.`,
        )
        return // Skip this edge
      }

      const sourceId = edge.source
      const targetId = edge.target
      const condition = edge.condition // string | null

      // Check if there's a condition AND if labels should be shown
      if (condition && showEdgeLabels) {
        lines.push(`  ${sourceId} -.${escapeMermaidLabel(condition)}.-> ${targetId}`)
      } else if (condition && !showEdgeLabels) {
        lines.push(`  ${sourceId} -.-> ${targetId}`)
      } else {
        lines.push(`  ${sourceId} --> ${targetId}`)
      }
    })

    // 6. Join all lines into a single string
    return lines.join('\n')
  }
}
