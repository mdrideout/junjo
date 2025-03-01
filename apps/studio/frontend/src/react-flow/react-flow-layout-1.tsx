import '@xyflow/react/dist/style.css'

import {
  addEdge,
  Background,
  ConnectionLineType,
  OnConnect,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'

import { useCallback } from 'react'
import { initialNodes, initialEdges } from './example-rf-data'
import layoutGraphWithDagre, { ReactFlowGraphDirection } from './dagre-layout-util'

export default function ReactFlowLayout1() {
  // Perform initial layout
  const { nodes: layoutedNodes, edges: layoutedEdges } = layoutGraphWithDagre({
    nodes: initialNodes,
    edges: initialEdges,
    direction: ReactFlowGraphDirection.LR,
  })

  // Local State
  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutedEdges)

  // onConnect: Runs when a connection is made between two nodes by the user
  const onConnect: OnConnect = useCallback(
    (params) => setEdges((eds) => addEdge({ ...params, type: ConnectionLineType.SmoothStep, animated: true }, eds)),
    [],
  )

  // Function to dynamically update the layout of the graph
  const onLayout = useCallback(
    (direction: ReactFlowGraphDirection) => {
      const { nodes: layoutedNodes, edges: layoutedEdges } = layoutGraphWithDagre({
        nodes: initialNodes,
        edges: initialEdges,
        direction,
      })

      setNodes([...layoutedNodes])
      setEdges([...layoutedEdges])
    },
    [nodes, edges],
  )

  // Render the graph
  return (
    <div className="w-dvw h-dvh">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        connectionLineType={ConnectionLineType.SmoothStep}
        defaultViewport={{ zoom: 1.0, x: 20, y: 20 }}
        style={{ backgroundColor: 'transparent', color: '#000' }}
      >
        {/* <Panel position="top-left">
          <button onClick={() => onLayout('TB')}>vertical layout</button>
          <button onClick={() => onLayout('LR')}>horizontal layout</button>
        </Panel> */}
        <Background />
      </ReactFlow>
    </div>
  )
}
