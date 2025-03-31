import { Node, Edge, Position } from '@xyflow/react'
import dagre from '@dagrejs/dagre'

export enum ReactFlowGraphDirection {
  LR = 'LR',
  TB = 'TB',
}

// Interfaces
export interface LayoutGraphWithDagreProps {
  nodes: Node[]
  edges: Edge[]
  direction?: ReactFlowGraphDirection
}
export interface LayoutGraphWithDagreResult {
  nodes: Node[]
  edges: Edge[]
}

/**
 * Dagre Layout Util
 *
 * A utility function to handle configuring the Dagre Graph, and performing
 * the layout of the nodes and edges.
 *
 * Layout library: Dagre
 * - https://github.com/dagrejs/dagre/wiki
 * - https://reactflow.dev/learn/layouting/layouting#dagre
 *
 * @param nodes
 * @param edges
 * @param direction
 * @returns
 */
export default function layoutGraphWithDagre(props: LayoutGraphWithDagreProps): LayoutGraphWithDagreResult {
  const { nodes, edges, direction = ReactFlowGraphDirection.TB } = props

  // Construct a new graph instance
  const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))

  // Size constants
  const nodeWidth = 175
  const nodeHeight = 40

  // Determine direction
  const isHorizontal = direction === ReactFlowGraphDirection.LR
  dagreGraph.setGraph({ rankdir: direction?.valueOf(), nodesep: 100, ranksep: 20 })

  nodes.forEach((node) => {
    node.style = {
      width: nodeWidth,
      height: nodeHeight,
      wordBreak: 'break-all',
      padding: '4px 6px',
      lineHeight: '1.2',
      fontSize: '11px',
      display: 'grid',
      placeItems: 'center',
      justifyItems: 'center',
    }
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  const newNodes: Node[] = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    const newNode: Node = {
      ...node,
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,

      // Shift the dagre node position (anchor=center center) to the top left
      // so it matches the React Flow node anchor point (top left).
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    }

    return newNode
  })

  const result: LayoutGraphWithDagreResult = { nodes: newNodes, edges }
  return result
}
