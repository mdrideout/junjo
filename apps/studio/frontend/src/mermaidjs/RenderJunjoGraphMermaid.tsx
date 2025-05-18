import { useCallback, useEffect, useMemo, useRef, useState } from 'react' // Import useState
import mermaid from 'mermaid'
import { extractJunjoIdFromMermaidElementId } from './mermaid-render-utils'
import { useAppDispatch, useAppSelector } from '../root-store/hooks'

import { RootState } from '../root-store/store'
import { identifyWorkflowChain, selectAllSpanChildSpans } from '../features/otel/store/selectors'
import { JunjoSpanType } from '../features/otel/store/schemas'
import { WorkflowDetailStateActions } from '../features/workflow-logs/workflow-detail/store/slice'

interface RenderJunjoGraphMermaidProps {
  mermaidFlowString: string
  mermaidUniqueId: string
  serviceName: string
  workflowSpanID: string
}

export default function RenderJunjoGraphMermaid(props: RenderJunjoGraphMermaidProps) {
  const { mermaidFlowString, mermaidUniqueId, serviceName, workflowSpanID } = props
  const dispatch = useAppDispatch()
  const svgContainerRef = useRef<HTMLDivElement>(null)
  const [highlightTrigger, setHighlightTrigger] = useState(0) // State to trigger re-render

  // Generate a unique ID for the container div and SVG
  const containerId = `mermaid-container-${mermaidUniqueId}`

  // MERMAID RENDER FIX: this ref will survive across the StrictMode double‑mount and block the 2nd run
  const strictModeFixHasRenderedRef = useRef<string>('')

  // SELECTORS
  const activeSpan = useAppSelector((state: RootState) => state.workflowDetailState.activeSpan)
  const workflowChain = useAppSelector((state: RootState) =>
    identifyWorkflowChain(state, {
      serviceName,
      spanID: workflowSpanID,
    }),
  )

  // 1. Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName,
      spanID: workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  // Get all spans for this workflow
  const workflowChildSpans = useAppSelector((state: RootState) =>
    selectAllSpanChildSpans(state, selectorProps),
  )
  const nodeSpans = workflowChildSpans.filter(
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
        // Set the active SetState event to the first event in this node
        dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))

        // Get the span with the junjo.id that matches the junjoID
        const clickedSpan = workflowChildSpans.find((span) => span.junjo_id === junjoID)
        if (clickedSpan) {
          dispatch(WorkflowDetailStateActions.handleSetActiveSpan(clickedSpan))
        }
      } else {
        console.warn('Could not extract Junjo ID from clicked element:', targetElement)
      }
    },
    [dispatch, workflowChildSpans],
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
        const clickedSpan = workflowChildSpans.find((span) => span.junjo_id === junjoID)
        if (clickedSpan) {
          dispatch(WorkflowDetailStateActions.handleSetActiveSpan(clickedSpan))
        }
      } else {
        console.warn('Could not extract Junjo ID from clicked element:', targetElement)
      }
    },
    [dispatch, workflowChildSpans],
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

  // --- Effect for Active Node Highlighting ---
  // This effect runs when the activeSpan changes or the container ref is available
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
    if (activeSpan) {
      // Construct the base ID prefix we expect
      const baseTargetId = `flowchart-${activeSpan.junjo_id}`

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
