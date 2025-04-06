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
   * rendering nodes marked as subgraphs correctly.
   *
   * @param {MermaidGraphDirection} direction - The overall direction of the flowchart (e.g., 'TB', 'LR'). Defaults to 'LR'.
   * @param {MermaidGraphDirection} subDirection - Optional direction for layout *within* subgraphs. Defaults to 'TB'.
   * @returns {string} A string containing the Mermaid flowchart definition.
   */
  toMermaid(
    direction: MermaidGraphDirection = 'LR',
    subDirection: MermaidGraphDirection = 'LR', // Default direction inside subgraphs
  ): string {
    const lines: string[] = []

    // Create a map for easy node lookup by ID
    const nodeMap = new Map<string, JNode>(this.graph.nodes.map((node) => [node.id, node]))

    // Sets to keep track of node roles
    const childrenNodeIds = new Set<string>()
    const subgraphContainerIds = new Set<string>()

    // 1. Preprocessing: Identify subgraph containers and their children
    this.graph.nodes.forEach((node) => {
      if (node.isSubgraph && node.children && node.children.length > 0) {
        subgraphContainerIds.add(node.id)
        node.children.forEach((childId) => {
          if (nodeMap.has(childId)) {
            // Only add if the child node actually exists
            childrenNodeIds.add(childId)
          } else {
            console.warn(
              `Subgraph ${node.id} ('${node.label}') lists child ID ${childId}, but this node was not found.`,
            )
          }
        })
      }
    })

    // 2. Start graph definition
    lines.push(`graph ${direction}`)

    // 3. Define top-level nodes (nodes that are NOT children of any subgraph AND are NOT subgraph containers themselves)
    this.graph.nodes.forEach((node) => {
      if (!childrenNodeIds.has(node.id) && !subgraphContainerIds.has(node.id)) {
        lines.push(`  ${node.id}[${escapeMermaidLabel(node.label)}]`)
      }
    })

    // 4. Define subgraphs and their children nodes
    this.graph.nodes.forEach((node) => {
      if (subgraphContainerIds.has(node.id)) {
        // Check if it's a subgraph container we identified
        lines.push(``) // Add empty line for readability
        lines.push(`  subgraph ${node.id} [${escapeMermaidLabel(node.label)}]`)
        lines.push(`    direction ${subDirection}`) // Set internal direction

        node.children?.forEach((childId) => {
          const childNode = nodeMap.get(childId)
          if (childNode) {
            // Define the child node INSIDE the subgraph block
            lines.push(`    ${childNode.id}[${escapeMermaidLabel(childNode.label)}]`)
          }
          // We already warned about missing children during preprocessing
        })
        lines.push(`  end`)
      }
    })

    // 5. Define all explicit edges from the graph definition
    lines.push(``) // Add empty line for readability
    this.graph.edges.forEach((edge) => {
      // Basic validation: Ensure source and target nodes were found during collection
      if (!nodeMap.has(edge.source) || !nodeMap.has(edge.target)) {
        console.warn(
          `Skipping edge '${edge.id}' because source ('${edge.source}') or target ('${edge.target}') node was not found.`,
        )
        return // Skip this edge
      }

      const sourceId = edge.source
      const targetId = edge.target
      const condition = edge.condition // string | null

      if (condition) {
        // Edge with a condition (label)
        lines.push(`  ${sourceId} --${escapeMermaidLabel(condition)}--> ${targetId}`)
      } else {
        // Edge without a condition
        lines.push(`  ${sourceId} --> ${targetId}`)
      }
    })

    // 6. Join all lines into a single string
    return lines.join('\n')
  }
}

// /**
//  * To React Flow (Clean Hierarchy for ELK + Custom Node Type)
//  *
//  * Converts the Junjo Graph JSON representation for React Flow,
//  * defining hierarchy via parentId and assigning a custom type
//  * to subgraph nodes for custom rendering with Handles.
//  *
//  * @param {ReactFlowGraphDirection} direction - Layout direction hint.
//  * @param {number} defaultSubgraphWidth - Placeholder width for subgraph nodes.
//  * @param {number} defaultSubgraphHeight - Placeholder height for subgraph nodes.
//  * @returns {ReactFlowInitialData} Initial data for React Flow.
//  */
// toReactFlow(
//   direction: ReactFlowGraphDirection = ReactFlowGraphDirection.LR,
//   defaultSubgraphWidth: number = 350,
//   defaultSubgraphHeight: number = 250,
// ): ReactFlowInitialData {
//   const nodeMap = new Map<string, JNode>(this.graph.nodes.map((node) => [node.id, node]))
//   const childToParentMap = new Map<string, string>()
//   const subgraphIds = new Set<string>() // Still useful to know which are containers

//   // 1. Preprocessing: Identify children and subgraph container IDs
//   this.graph.nodes.forEach((node) => {
//     if (node.isSubgraph && node.children) {
//       subgraphIds.add(node.id)
//       node.children.forEach((childId) => {
//         if (nodeMap.has(childId)) {
//           childToParentMap.set(childId, node.id)
//         } else {
//           console.warn(
//             `Subgraph node ${node.id} ('${node.label}') lists child ${childId}, but it was not found.`,
//           )
//         }
//       })
//     }
//   })

//   // 2. Map JNodes to React Flow Nodes (NO PROXY NODES)
//   const nodes: RFNode[] = this.graph.nodes.map((node) => {
//     const isChild = childToParentMap.has(node.id)
//     const parentId = isChild ? childToParentMap.get(node.id) : undefined
//     const isSubgraph = subgraphIds.has(node.id)

//     // Base React Flow node structure
//     const rfNode: RFNode = {
//       id: node.id,
//       // *** Use a CUSTOM TYPE for subgraph containers ***
//       type: isSubgraph ? 'junjoSubgraph' : undefined, // Signal custom rendering needed
//       data: { label: node.label },
//       position: { x: 0, y: 0 }, // Placeholder for layout algorithm
//       parentId: parentId,
//       extent: isChild ? 'parent' : undefined,
//     }

//     // Add style with dimensions ONLY to the subgraph container nodes
//     if (isSubgraph) {
//       rfNode.style = {
//         width: defaultSubgraphWidth,
//         height: defaultSubgraphHeight,
//       }
//     }

//     return rfNode
//   })

//   // 3. Map JEdges to React Flow Edges (NO REDIRECTION)
//   const edges: RFEdge[] = this.graph.edges
//     .filter((edge) => nodeMap.has(edge.source) && nodeMap.has(edge.target))
//     .map((edge) => ({
//       id: edge.id,
//       source: edge.source, // Use original source ID
//       target: edge.target, // Use original target ID
//       label: edge.condition ?? undefined,
//       style: {
//         strokeDasharray: edge.condition ? '6 4' : undefined,
//       },
//       // Note: We don't specify source/target handles here. The custom node's
//       // default Handles will be used by React Flow if handle IDs aren't specified.
//     }))

//   // 4. Return the structured data
//   return {
//     direction,
//     nodes, // Clean list without proxy nodes
//     edges, // Clean list with original source/targets
//   }
// }
