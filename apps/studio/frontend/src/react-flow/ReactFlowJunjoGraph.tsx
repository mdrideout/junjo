import '@xyflow/react/dist/style.css'

import {
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  ConnectionLineType,
  OnEdgesChange,
  OnNodesChange,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Node,
  type Edge,
  FitViewOptions,
} from '@xyflow/react'

import layoutGraphWithDagre, { ReactFlowGraphDirection } from './dagre-layout-util'
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import { useCallback, useEffect, useState } from 'react'

export type ReactFlowJunjoGraphProps = {
  junjoGraph: JunjoGraph
  direction?: ReactFlowGraphDirection
}

/**
 * React Flow Junjo Graph
 *
 * Renders a React Flow graph from a JunjoGraph instance.
 */
export default function ReactFlowJunjoGraph(props: ReactFlowJunjoGraphProps) {
  const { junjoGraph, direction } = props

  // Get initial graph nodes and perform the layout
  const { nodes: initialNodes, edges: initialEdges } = junjoGraph.toReactFlow()
  const { nodes: layoutedNodes, edges: layoutedEdges } = layoutGraphWithDagre({
    nodes: initialNodes,
    edges: initialEdges,
    direction: direction ?? ReactFlowGraphDirection.LR, //Handle undefined direction
  })

  // Local State
  const [nodes, setNodes] = useState<Node[]>(layoutedNodes)
  const [edges, setEdges] = useState<Edge[]>(layoutedEdges)

  // Handle node changes
  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes],
  )

  // Handle edge changes
  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges],
  )

  // Render the graph
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      defaultViewport={{ zoom: 1.0, x: 20, y: 20 }}
      style={{ backgroundColor: 'transparent', color: '#000' }}
      proOptions={{ hideAttribution: true }}
    >
      <Background />
    </ReactFlow>
  )
}
