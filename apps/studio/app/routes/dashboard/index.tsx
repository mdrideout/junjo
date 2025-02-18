import { addEdge, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'

import '@xyflow/react/dist/style.css'
import { useCallback } from 'react'

const initialNodes = [
  {
    id: '4347435328',
    data: { label: 'CountNode' },
    position: { x: 0.0, y: 0.0 },
  },
  {
    id: '4347435664',
    data: { label: 'IncrementNode' },
    position: { x: 0.0, y: 100 },
  },
  {
    id: '4347436000',
    data: { label: 'SetWarningNode' },
    position: { x: 150, y: 200 },
  },
  {
    id: '4347436336',
    data: { label: 'FinalNode' },
    position: { x: 0.0, y: 300 },
  },
]
const initialEdges = [
  {
    id: '4347435328-4347435664',
    source: '4347435328',
    target: '4347435664',
    label: null,
  },
  {
    id: '4347435664-4347436000',
    source: '4347435664',
    target: '4347436000',
    label: 'count_over_10',
  },
  {
    id: '4347436000-4347436336',
    source: '4347436000',
    target: '4347436336',
    label: null,
  },
  {
    id: '4347435664-4347436336',
    source: '4347435664',
    target: '4347436336',
    label: null,
  },
]

export default function DashboardIndex() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  const onConnect = useCallback((params: any) => setEdges((eds) => addEdge(params, eds)), [setEdges])

  return (
    <div>
      <p>Sample ReactFlow from output.</p>
      <div className="w-dvw h-dvh text-black">
        <ReactFlow
          nodes={initialNodes}
          edges={initialEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
        />
      </div>
    </div>
  )
}
