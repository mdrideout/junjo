import '@xyflow/react/dist/style.css'

import {
  applyNodeChanges,
  applyEdgeChanges,
  Background,
  OnEdgesChange,
  OnNodesChange,
  ReactFlow,
  type Node,
  type Edge,
} from '@xyflow/react'

import layoutGraphWithELK from '../elk-layout-util'
import { JunjoGraph } from '../../junjo-graph/junjo-graph'
import { useCallback, useEffect, useState } from 'react'
import { ReactFlowGraphDirection } from '../schemas'

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

  console.log('Mermaid flow json:\n', junjoGraph.toMermaid())
  console.log('React Flow Json:\n', junjoGraph.toReactFlow())

  // Initialize state: empty nodes/edges initially, add loading state
  const [nodes, setNodes] = useState<Node[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)

  // useEffect hook to run layout calculation
  useEffect(() => {
    // Flag to prevent state update if component unmounts while layout is running
    let isMounted = true
    setIsLoading(true) // Start loading indicator

    // Get the initial structure (unlayouted)
    // Pass the resolved direction to toReactFlow
    const { nodes: initialNodes, edges: initialEdges } = junjoGraph.toReactFlow(direction)

    // --- Debugging ---
    // console.log('React Flow Json (Input to ELK util):\n', JSON.stringify({nodes: initialNodes, edges: initialEdges}, null, 2));
    // --- End Debugging ---

    // Call the asynchronous layout function
    layoutGraphWithELK({ nodes: initialNodes, edges: initialEdges, direction })
      .then(({ nodes: layoutedNodes, edges: layoutedEdges }) => {
        // Check if component is still mounted before updating state
        if (isMounted) {
          setNodes(layoutedNodes)
          // Use the edges returned by layout function (usually same as initialEdges)
          setEdges(layoutedEdges)
        }
      })
      .catch((error) => {
        console.error('ELK layout failed:', error)
        // Handle layout error: fall back to unlayouted nodes or show an error state
        if (isMounted) {
          setNodes(initialNodes) // Show unlayouted nodes as fallback
          setEdges(initialEdges)
        }
      })
      .finally(() => {
        // Ensure loading state is turned off even if component unmounted quickly
        if (isMounted) {
          setIsLoading(false)
        }
      })

    // Cleanup function: runs when component unmounts or dependencies change
    return () => {
      isMounted = false // Prevent state updates on unmounted component
    }
    // Dependencies: Re-run layout if the graph data or direction prop changes
  }, [junjoGraph, direction])

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

  if (isLoading) {
    // Replace with a spinner or skeleton screen if desired
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100%',
          minHeight: '200px',
        }}
      >
        Calculating layout...
      </div>
    )
  }

  // Render the graph
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      defaultViewport={{ zoom: 1.0, x: 10, y: 10 }}
      style={{ backgroundColor: '#f4f4f5', color: '#000', borderRadius: '6px' }}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
    >
      <Background color="transparent" />
    </ReactFlow>
  )
}
