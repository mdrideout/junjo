import { ReactFlowGraphDirection } from '../react-flow/dagre-layout-util'
import { ReactFlowInitialData } from '../react-flow/schemas'
import { JunjoGraphError } from './errors'
import { JEdge, JGraph, JGraphSchema, JNode } from './schemas'
import { Edge as RFEdge, Node as RFNode } from '@xyflow/react' // Import correct types

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
   * To React Flow
   *
   * Converts the generic Junjo Graph JSON representation into a data structure
   * optimized for use with React Flow.
   * @param {ReactFlowGraphDirection} direction is the horizontal or vertical direction the graph should render
   */
  toReactFlow(direction: ReactFlowGraphDirection = ReactFlowGraphDirection.LR): ReactFlowInitialData {
    const nodes: RFNode[] = this.graph.nodes.map((node) => ({
      id: node.id,
      // type: node.type, //If you have custom node types, this is how they will be associated
      data: { label: node.label },
      position: { x: 0, y: 0 }, // Default position; layout will adjust.
    }))

    const edges: RFEdge[] = this.graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.condition, // Label will display the condition
      style: { strokeDasharray: edge.condition ? '5, 3' : '' }, // Conditional dotted line
    }))

    return { direction, nodes, edges }
  }
}
