import { Edge, Node } from '@xyflow/react'

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

// Define ReactFlow direction type
export enum ReactFlowGraphDirection {
  TB = 'TB',
  LR = 'LR',
  RL = 'RL',
  BT = 'BT',
}
