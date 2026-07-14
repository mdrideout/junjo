import mermaid from 'mermaid'
import { useCallback, useEffect, useRef, useState } from 'react'
import { extractGraphNodeIdFromMermaidElementId } from './mermaid-render-utils'
import {
  findRenderedGraphNodeIdForSpan,
  findSpanForRenderedGraphNodeId,
} from './junjo-graph-span-matching'
import { useAppDispatch, useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'
import { JunjoSpanType, OtelSpan } from '../features/traces/schemas/schemas'
import { WorkflowDetailStateActions } from '../features/junjo-data/workflow-detail/store/slice'
import { JGraph } from '../junjo-graph/schemas'
import {
  selectActiveSpanFirstJunjoParent,
  selectTraceSpansForTraceId,
} from '../features/traces/store/selectors'
import { useNavigate, useParams } from 'react-router'
import { wrapSpan } from '../features/traces/utils/span-accessor'

interface RenderJunjoGraphMermaidProps {
  graphSnapshot: JGraph
  traceId: string
  workflowChain: OtelSpan[]
  mermaidFlowString: string
  mermaidUniqueId: string
  workflowSpanId: string
}

export default function RenderJunjoGraphMermaid(props: RenderJunjoGraphMermaidProps) {
  const { graphSnapshot, traceId, workflowChain, mermaidFlowString, mermaidUniqueId } = props
  const dispatch = useAppDispatch()
  const svgContainerRef = useRef<HTMLDivElement>(null)
  const [highlightTrigger, setHighlightTrigger] = useState(0) // State to trigger re-render
  const navigate = useNavigate()
  const { serviceName, traceId: traceIdParam, workflowSpanId } = useParams()

  // Generate a unique ID for the container div and SVG
  const containerId = `mermaid-container-${mermaidUniqueId}`

  // MERMAID RENDER FIX: this ref will survive across the StrictMode double‑mount and block the 2nd run
  const strictModeFixHasRenderedRef = useRef<string>('')

  // SELECTORS
  const firstJunjoSpan = useAppSelector((state: RootState) => selectActiveSpanFirstJunjoParent(state))
  const traceSpans = useAppSelector((state: RootState) => selectTraceSpansForTraceId(state, { traceId }))

  const graphSpans = traceSpans.filter((span) => {
    const spanType = wrapSpan(span).junjoSpanType
    return (
      spanType === JunjoSpanType.NODE ||
      spanType === JunjoSpanType.SUBFLOW ||
      spanType === JunjoSpanType.RUN_CONCURRENT
    )
  })

  const findSpanForGraphNodeId = useCallback(
    (graphNodeId: string) => findSpanForRenderedGraphNodeId(graphSnapshot, graphNodeId, graphSpans),
    [graphSnapshot, graphSpans],
  )

  /**
   * Attach listeners to the elements, and annotate where appropriate
   */
  const handleGraphNodeClick = useCallback(
    (event: MouseEvent) => {
      const targetElement = event.currentTarget as SVGGElement
      const nodeIdAttr = targetElement?.id

      const graphNodeId = extractGraphNodeIdFromMermaidElementId(nodeIdAttr)
      if (graphNodeId) {
        const clickedSpan = findSpanForGraphNodeId(graphNodeId)
        if (clickedSpan) {
          dispatch(WorkflowDetailStateActions.setActiveSpan(clickedSpan))
          dispatch(WorkflowDetailStateActions.setActiveStateEvent(null))

          // Preserve existing params and set the new spanId
          const newPath = `/workflows/${serviceName}/${traceIdParam}/${workflowSpanId}/${clickedSpan.span_id}`
          navigate(newPath, {
            replace: true,
          })
        }
      } else {
        console.warn('Could not extract graph node ID from clicked element:', targetElement)
      }
    },
    [dispatch, findSpanForGraphNodeId, navigate, serviceName, traceIdParam, workflowSpanId],
  )

  /**
   * Attach listeners to the elements, and annotate where appropriate
   */
  const attachListenersAndAnnotate = useCallback(
    (container: HTMLDivElement) => {
      const renderedGraphElements = container.querySelectorAll('.node, .cluster')
      renderedGraphElements.forEach((graphElement) => {
        const graphNodeId = extractGraphNodeIdFromMermaidElementId(graphElement.id)
        const utilizedNodeSpan = graphNodeId ? findSpanForGraphNodeId(graphNodeId) : undefined
        if (!utilizedNodeSpan) {
          graphElement.classList.add('graph-element-not-utilized')
        } else {
          if (wrapSpan(utilizedNodeSpan).isSubflow) {
            graphElement.classList.add('node-subflow')
          }
          graphElement.addEventListener('click', handleGraphNodeClick as EventListener)
        }

        if (utilizedNodeSpan && wrapSpan(utilizedNodeSpan).hasFailureSignal) {
          graphElement.classList.add('node-has-exception')
        }
      })
    },
    [findSpanForGraphNodeId, handleGraphNodeClick],
  )

  /**
   * Rerender The Mermaid Flow Diagram on Changes
   */
  useEffect(() => {
    const stringIsRendered = mermaidFlowString == strictModeFixHasRenderedRef.current

    // Check if the component has rendered before
    // Fixes an issue with React.StrictMode causing double rendering and breaking the SVG
    if (stringIsRendered) {
      console.log('Component has already rendered, skipping re-render.')
      return
    }

    // Set the flag to the currently rendered string
    strictModeFixHasRenderedRef.current = mermaidFlowString

    // Ensure the container exists before proceeding
    if (!svgContainerRef.current) {
      return
    }

    // Handle valid flow string: Render the diagram
    if (mermaidFlowString) {
      try {
        const svgId = `mermaid-svg-${mermaidUniqueId}` // Unique ID for the SVG itself

        // mermaid.render will use the theme set by mermaid.initialize()
        mermaid
          .render(svgId, mermaidFlowString)
          .then(({ svg, bindFunctions }) => {
            if (svgContainerRef.current) {
              // Clear previous content *before* adding new SVG
              svgContainerRef.current.innerHTML = ''
              svgContainerRef.current.innerHTML = svg // Inject the rendered SVG into the container

              attachListenersAndAnnotate(svgContainerRef.current) // Attach listeners to the nodes

              // Bind any interactive functions if necessary
              if (bindFunctions) {
                bindFunctions(svgContainerRef.current)
              }
              // Run the highlight trigger to ensure the active node is highlighted
              setHighlightTrigger((prev) => prev + 1)
            }
          })
          .catch((error) => {
            console.error('Mermaid rendering failed:', error)
            if (svgContainerRef.current) {
              svgContainerRef.current.innerHTML = `Error rendering diagram: ${error.message}`
            }
          })
      } catch (error) {
        console.error('Mermaid syntax error or other issue:', error)
        if (svgContainerRef.current) {
          svgContainerRef.current.innerHTML = `Error parsing diagram: ${error}`
        }
      }
    }
  }, [attachListenersAndAnnotate, mermaidFlowString, mermaidUniqueId])

  // --- Effect for Junjo Node Highlighting ---
  // This effect runs when the firstJunjoSpan changes or the container ref is available
  // This will highlight the first found JunjoSpan based on the activeSpan
  useEffect(() => {
    // Ensure the container ref is available
    if (!svgContainerRef.current) {
      console.warn('Mermaid container ref not available yet.')
      return
    }

    // --- Remove active class efficiently ---
    // Find the currently active node *within this container* and remove the class
    const prevActiveNode = svgContainerRef.current.querySelector('.mermaid-node-active')
    if (prevActiveNode) {
      prevActiveNode.classList.remove('mermaid-node-active')
    }

    // --- Add active class to the new active node ---
    if (firstJunjoSpan) {
      const graphNodeId = findRenderedGraphNodeIdForSpan(graphSnapshot, firstJunjoSpan)
      if (!graphNodeId) {
        return
      }

      const baseTargetId = `flowchart-${graphNodeId}`

      // Use querySelector with an attribute "starts with" selector [id^=...]
      // Query within the specific svgContainerRef.current for better scoping
      // Use CSS.escape for robustness with potential special characters in IDs
      const activeNode = svgContainerRef.current.querySelector(
        `[id^="${CSS.escape(baseTargetId)}"], #${CSS.escape(graphNodeId)}`,
      )

      if (
        activeNode &&
        (activeNode.classList.contains('node') || activeNode.classList.contains('cluster'))
      ) {
        activeNode.classList.add('mermaid-node-active')

        // Scroll to the active node
        ;(activeNode as HTMLElement).scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'center',
        })
      }
    }
    // Dependencies: Ensure all variables used inside are listed, including the container ref's existence indirectly
  }, [firstJunjoSpan, graphSnapshot, highlightTrigger])

  // --- Effect for subflow highlighting ---
  // This effect runs when the workflowChain changes to highlight subflow nodes
  // inside the workflow chain
  useEffect(() => {
    // Ensure the container ref is available
    if (!svgContainerRef.current) {
      console.warn('Mermaid container ref not available yet.')
      return
    }
    const containerElement = svgContainerRef.current

    // Find all subflow nodes within the container
    const subflowNodes = containerElement.querySelectorAll('.node-subflow')
    const activeWorkflowNodeIds = new Set(
      workflowChain
        .map((span) => findRenderedGraphNodeIdForSpan(graphSnapshot, span))
        .filter((nodeId): nodeId is string => nodeId !== null),
    )

    subflowNodes.forEach((node) => {
      // Remove the '.node-subflow-active' class if it exists
      node.classList.remove('node-subflow-active')

      // Extract the Junjo ID from the node's ID
      const graphNodeId = extractGraphNodeIdFromMermaidElementId(node.id)

      // Check if this node-subflow is part of the active workflowChain
      const isActiveSubflow = graphNodeId !== null && activeWorkflowNodeIds.has(graphNodeId)
      if (isActiveSubflow) {
        node.classList.add('node-subflow-active')
      }
    })
  }, [graphSnapshot, workflowChain, highlightTrigger])

  // --- Render the Mermaid diagram ---
  // Render the container div where the SVG will be placed
  // console.log('Rendering mermaid diagram string:\n', mermaidFlowString)
  return <div ref={svgContainerRef} className={'mermaid-container'} id={containerId} />
}
