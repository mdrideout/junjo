import mermaid from 'mermaid'
import { useCallback, useEffect, useRef, useState } from 'react'
import { extractJunjoIdFromMermaidElementId } from './mermaid-render-utils'
import { useAppDispatch, useAppSelector } from '../root-store/hooks'
import { RootState } from '../root-store/store'
import { JunjoSpanType, OtelSpan } from '../features/traces/schemas/schemas'
import { WorkflowDetailStateActions } from '../features/junjo-data/workflow-detail/store/slice'
import {
  selectActiveSpanFirstJunjoParent,
  selectTraceSpansForTraceId,
} from '../features/traces/store/selectors'

interface RenderJunjoGraphMermaidProps {
  traceId: string
  workflowChain: OtelSpan[]
  mermaidFlowString: string
  mermaidUniqueId: string
  workflowSpanId: string
}

export default function RenderJunjoGraphMermaid(props: RenderJunjoGraphMermaidProps) {
  const { traceId, workflowChain, mermaidFlowString, mermaidUniqueId } = props
  const dispatch = useAppDispatch()
  const svgContainerRef = useRef<HTMLDivElement>(null)
  const [highlightTrigger, setHighlightTrigger] = useState(0) // State to trigger re-render

  // Generate a unique ID for the container div and SVG
  const containerId = `mermaid-container-${mermaidUniqueId}`

  // MERMAID RENDER FIX: this ref will survive across the StrictMode double‑mount and block the 2nd run
  const strictModeFixHasRenderedRef = useRef<string>('')

  // SELECTORS
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const firstJunjoSpan = useAppSelector((state: RootState) => selectActiveSpanFirstJunjoParent(state))
  const traceSpans = useAppSelector((state: RootState) => selectTraceSpansForTraceId(state, { traceId }))

  // Identify Node / Subflow Spans
  const nodeSpans = traceSpans.filter(
    (span) => span.junjo_span_type === JunjoSpanType.NODE || span.junjo_span_type === JunjoSpanType.SUBFLOW,
  )

  /**
   * Attach listeners to the elements, and annotate where appropriate
   */
  const attachListenersAndAnnotate = (container: HTMLDivElement) => {
    const existing = container.querySelectorAll('.node')
    existing.forEach((node) => {
      const junjoNodeId = extractJunjoIdFromMermaidElementId(node.id)
      const utilizedNodeSpan = nodeSpans.find((s) => s.junjo_id === junjoNodeId)
      if (!utilizedNodeSpan) {
        node.classList.add('graph-element-not-utilized')
      } else if (utilizedNodeSpan.junjo_span_type === JunjoSpanType.NODE) {
        node.addEventListener('click', handleNodeClick as EventListener)
      } else {
        node.classList.add('node-subflow')
        node.addEventListener('click', handleSubflowClick as EventListener)
      }

      // Annotate exceptions
      const hasException = utilizedNodeSpan?.events_json.some((event) => {
        return event.attributes && event.attributes['exception.type'] !== undefined
      })
      if (hasException) {
        node.classList.add('node-has-exception')
      }
    })
  }

  // --- Node Click Handler Definition ---
  // Use useCallback to ensure the function reference is stable for add/removeEventListener
  const handleNodeClick = useCallback(
    (event: MouseEvent) => {
      // Use currentTarget to get the element the listener was attached to (<g class="node">)
      const targetElement = event.currentTarget as SVGGElement // Type assertion
      const nodeIdAttr = targetElement?.id

      // Get the ID from the mermaid element
      const junjoID = extractJunjoIdFromMermaidElementId(nodeIdAttr)
      if (junjoID) {
        // Get the span with the junjo.id that matches the junjoID
        const clickedSpan = traceSpans.find((span) => span.junjo_id === junjoID)
        if (clickedSpan) {
          dispatch(WorkflowDetailStateActions.setActiveSpan(clickedSpan))
        }
      } else {
        console.warn('Could not extract Junjo ID from clicked element:', targetElement)
      }
    },
    [dispatch, traceSpans],
  )

  // --- Subflow Click Handler ---
  const handleSubflowClick = useCallback(
    (event: MouseEvent) => {
      const targetElement = event.currentTarget as SVGGElement
      const nodeIdAttr = targetElement?.id
      const junjoID = extractJunjoIdFromMermaidElementId(nodeIdAttr)
      if (junjoID) {
        dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

        // Get the span with the junjo.id that matches the junjoID
        const clickedSpan = traceSpans.find((span) => span.junjo_id === junjoID)
        if (clickedSpan) {
          dispatch(WorkflowDetailStateActions.setActiveSpan(clickedSpan))
        }
      } else {
        console.warn('Could not extract Junjo ID from clicked element:', targetElement)
      }
    },
    [dispatch, traceSpans],
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
  }, [mermaidFlowString, mermaidUniqueId])

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
      // Construct the base ID prefix we expect
      const baseTargetId = `flowchart-${firstJunjoSpan.junjo_id}`

      // Use querySelector with an attribute "starts with" selector [id^=...]
      // Query within the specific svgContainerRef.current for better scoping
      // Use CSS.escape for robustness with potential special characters in IDs
      const activeNode = svgContainerRef.current.querySelector(`[id^="${CSS.escape(baseTargetId)}"]`)

      if (activeNode && activeNode.classList.contains('node')) {
        // Extra check that it's a node group
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
  }, [activeSpan, svgContainerRef, highlightTrigger])

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
    subflowNodes.forEach((node) => {
      // Remove the '.node-subflow-active' class if it exists
      node.classList.remove('node-subflow-active')

      // Extract the Junjo ID from the node's ID
      const junjoNodeId = extractJunjoIdFromMermaidElementId(node.id)

      // Check if this node-subflow is part of the active workflowChain
      const isActiveSubflow = workflowChain.some((span) => span.junjo_id === junjoNodeId)
      if (isActiveSubflow) {
        node.classList.add('node-subflow-active')
      }
    })
  }, [workflowChain, svgContainerRef, highlightTrigger])

  // --- Render the Mermaid diagram ---
  // Render the container div where the SVG will be placed
  // console.log('Rendering mermaid diagram string:\n', mermaidFlowString)
  return <div ref={svgContainerRef} className={'mermaid-container'} id={containerId} />
}
