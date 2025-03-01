import { Edge, Node } from '@xyflow/react'
import { ReactFlowGraphDirection } from './dagre-layout-util'

/**
 * React Flow Initial Data
 *
 * This data structure can be fed into a React Flow component for rendering.
 */
export type ReactFlowInitialData = {
  direction: ReactFlowGraphDirection
  nodes: Node[]
  edges: Edge[]
}
