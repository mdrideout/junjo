import { Node, Edge, Position } from '@xyflow/react'
import ELK, { ElkNode, ElkExtendedEdge, LayoutOptions } from 'elkjs/lib/elk.bundled.js'
import { ReactFlowGraphDirection } from './schemas'
import { calculateNodeSize } from './elk-layout-helpers'

export interface LayoutGraphProps {
  nodes: Node[]
  edges: Edge[]
  direction?: ReactFlowGraphDirection
}

export interface LayoutGraphResult {
  nodes: Node[]
  edges: Edge[]
}

const getElkDirection = (direction: ReactFlowGraphDirection): 'RIGHT' | 'LEFT' | 'DOWN' | 'UP' => {
  switch (direction) {
    case ReactFlowGraphDirection.LR:
      return 'RIGHT'
    case ReactFlowGraphDirection.RL:
      return 'LEFT'
    case ReactFlowGraphDirection.BT:
      return 'UP'
    case ReactFlowGraphDirection.TB:
    default:
      return 'DOWN'
  }
}

// Define common ELK layout options
const elkLayoutOptions: LayoutOptions = {
  'elk.algorithm': 'layered',
  'elk.layered.spacing.nodeNodeBetweenLayers': '90',
  'elk.spacing.nodeNode': '70',
  'elk.edgeRouting': 'ORTHOGONAL',
}

// Instantiate the ELKjs worker
const elk = new ELK()

/**
 * Asynchronous layout function using ELKjs.
 */
export default async function layoutGraphWithELK(props: LayoutGraphProps): Promise<LayoutGraphResult> {
  const { nodes: initialNodes, edges, direction = ReactFlowGraphDirection.TB } = props

  const defaultNodeWidth = 175 // Used as minimum/fallback
  const defaultNodeHeight = 40
  const subgraphMinWidth = 275 // Keep separate defaults for subgraphs
  const subgraphMinHeight = 160

  // --- 1. Build the hierarchical ELK graph structure ---
  const elkNodeMap = new Map<string, ElkNode>()
  const rootElkChildren: ElkNode[] = []

  // Font style used in React Flow nodes (MUST MATCH YOUR CSS)
  // IMPORTANT: Update this to match the font used in your node components
  const nodeFontStyle = '12px sans-serif'

  // Create all ELK nodes first, calculating sizes
  initialNodes.forEach((node) => {
    const labelValue = node.data?.label
    const labelText = typeof labelValue === 'string' && labelValue.trim() !== '' ? labelValue : node.id
    const isSubgraphType = node.type === 'junjoSubgraph' // Use your custom type name

    let nodeWidth: number
    let nodeHeight: number

    if (isSubgraphType) {
      // Keep using explicit or larger default sizes for subgraph containers
      // Reading from node.style allows overriding defaults via toReactFlow
      nodeWidth = typeof node.style?.width === 'number' ? node.style.width : subgraphMinWidth
      nodeHeight = typeof node.style?.height === 'number' ? node.style.height : subgraphMinHeight
    } else {
      // Calculate size for regular nodes based on label content
      const calculatedSize = calculateNodeSize(
        labelText,
        nodeFontStyle,
        20,
        10,
        defaultNodeWidth,
        defaultNodeHeight,
      )
      nodeWidth = calculatedSize.width
      nodeHeight = calculatedSize.height
    }

    const elkNode: ElkNode = {
      id: node.id,
      width: nodeWidth, // Use calculated or explicit width
      height: nodeHeight, // Use calculated or explicit height
      labels: [{ text: labelText }],
      layoutOptions: {
        ...(isSubgraphType && {
          'elk.padding': '[top=30, left=30, bottom=30, right=30]',
        }),
      },
      ...(isSubgraphType && { children: [] }),
    }
    elkNodeMap.set(node.id, elkNode)
  })

  // Build the hierarchy
  initialNodes.forEach((node) => {
    const elkNode = elkNodeMap.get(node.id)
    if (!elkNode) return

    if (node.parentId) {
      const parentElkNode = elkNodeMap.get(node.parentId)
      if (parentElkNode?.children) {
        // Check children array exists
        parentElkNode.children.push(elkNode)
      } else {
        console.warn(
          `Parent node ${node.parentId} not found or not a group for child ${node.id}. Adding child to root.`,
        )
        rootElkChildren.push(elkNode)
      }
    } else {
      rootElkChildren.push(elkNode)
    }
  })

  // Transform React Flow edges to ELK edges
  const elkEdges: ElkExtendedEdge[] = edges.map((edge) => ({
    id: edge.id,
    sources: [edge.source],
    targets: [edge.target],
  }))

  // Construct the final ELK graph input object
  const elkGraphToLayout: ElkNode = {
    id: 'root',
    layoutOptions: {
      ...elkLayoutOptions,
      'elk.direction': getElkDirection(direction),
    },
    children: rootElkChildren,
    edges: elkEdges,
  }

  // --- 2. Run ELK Layout ---
  try {
    // console.log("--- Sending Graph to ELK ---", JSON.stringify(elkGraphToLayout, null, 2));
    const layoutedGraph = await elk.layout(elkGraphToLayout)
    // console.log("--- Received Graph from ELK ---", JSON.stringify(layoutedGraph, null, 2));

    // --- 3. Map ELK positions back to React Flow Nodes ---
    const positionMap = new Map<string, { x: number; y: number }>()

    function extractPositions(node: ElkNode) {
      if (typeof node.x === 'number' && typeof node.y === 'number') {
        positionMap.set(node.id, { x: node.x, y: node.y })
      } else if (node.id !== 'root') {
        console.warn(
          `ELK node ${node.id} ('${node.labels?.[0]?.text}') did not receive valid x/y coordinates.`,
        )
      }
      if (node.children) {
        node.children.forEach(extractPositions)
      }
    }
    extractPositions(layoutedGraph)

    // Update original nodes with new positions AND calculated dimensions in style
    const layoutedNodes = initialNodes.map((node) => {
      const position = positionMap.get(node.id)
      // Retrieve the dimensions that were calculated and passed to ELK
      const elkNodeData = elkNodeMap.get(node.id)
      const calculatedWidth = elkNodeData?.width
      const calculatedHeight = elkNodeData?.height

      // Determine handle positions (same as before)
      const isHorizontal =
        direction === ReactFlowGraphDirection.LR || direction === ReactFlowGraphDirection.RL
      const targetPosition = isHorizontal ? Position.Left : Position.Top
      const sourcePosition = isHorizontal ? Position.Right : Position.Bottom

      const finalPosition = position ?? node.position ?? { x: 0, y: 0 }
      if (!position) {
        console.warn(`Position for node ${node.id} not found in ELK result. Using original/default position.`)
      }

      return {
        ...node, // Keep original data, type, parentId, extent etc.
        targetPosition,
        sourcePosition,
        position: finalPosition, // Set the calculated or fallback position
        // *** IMPORTANT: Apply calculated size to style for React Flow rendering ***
        style: {
          // ...node.style, // Keep original style if any
          width: calculatedWidth, // Ensure RF renders node at the size ELK used
          height: calculatedHeight, // Ensure RF renders node at the size ELK used
        },
      }
    })

    return { nodes: layoutedNodes, edges: edges }
  } catch (layoutError) {
    console.error('Error during ELK layout:', layoutError)
    return { nodes: initialNodes, edges }
  }
}
