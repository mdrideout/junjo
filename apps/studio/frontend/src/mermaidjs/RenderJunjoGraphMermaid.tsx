import { useCallback, useEffect, useMemo, useRef, useState } from 'react' // Import useState
import mermaid from 'mermaid'
import { useActiveNodeContext } from '../features/workflow-logs/workflow-detail/ActiveNodeContext'
import { extractMermaidNodeId } from './mermaid-render-utils'
import { useAppSelector } from '../root-store/hooks'

import { RootState } from '../root-store/store'
import { selectAllWorkflowChildSpans, selectAllWorkflowStateEvents } from '../features/otel/store/selectors'
import { JunjoSpanType } from '../features/otel/store/schemas'

interface RenderJunjoGraphMermaidProps {
  mermaidFlowString: string
  mermaidUniqueId: string
  serviceName: string
  workflowSpanID: string
}

// Base Mermaid configuration - customize as needed
// startOnLoad: false is important when using mermaid.render() manually
const mermaidBaseConfig = {
  startOnLoad: false,
  // securityLevel: 'loose', // Example other config
}

export default function RenderJunjoGraphMermaid(props: RenderJunjoGraphMermaidProps) {
  const { mermaidFlowString, mermaidUniqueId, serviceName, workflowSpanID } = props
  const { activeNodeSetStateEvent, setActiveNodeSetStateEvent, setScrollToPatchId } = useActiveNodeContext()

  // Append active styles for the active set state event node
  const activeSetStateEventNodeId = activeNodeSetStateEvent?.attributes['junjo.node.id'] ?? ''

  // 1. Memoize the props object for the selector
  const selectorProps = useMemo(
    () => ({
      serviceName,
      workflowSpanID,
    }),
    [serviceName, workflowSpanID],
  )

  // Get state events for this Node ID
  const workflowStateEvents = useAppSelector((state: RootState) =>
    selectAllWorkflowStateEvents(state, selectorProps),
  )

  // Get all spans for this workflow
  const workflowChildSpans = useAppSelector((state: RootState) =>
    selectAllWorkflowChildSpans(state, selectorProps),
  )
  const nodeSpans = workflowChildSpans.filter(
    (span) => span.junjo_span_type === JunjoSpanType.NODE || span.junjo_span_type === JunjoSpanType.SUBFLOW,
  )

  // Generate a unique ID for the container div and SVG
  const containerId = `mermaid-container-${mermaidUniqueId}`
  const svgContainerRef = useRef<HTMLDivElement>(null)
  // State to trigger re-render when the OS theme changes
  const [themeVersion, setThemeVersion] = useState(0)

  // --- Node Click Handler Definition ---
  // Use useCallback to ensure the function reference is stable for add/removeEventListener
  const handleNodeClick = useCallback(
    (event: MouseEvent) => {
      // Use currentTarget to get the element the listener was attached to (<g class="node">)
      const targetElement = event.currentTarget as SVGGElement // Type assertion
      const nodeIdAttr = targetElement?.id
      const mermaidNodeId = extractMermaidNodeId(nodeIdAttr)

      if (mermaidNodeId) {
        const nodeStateEvents = workflowStateEvents.filter(
          (event) => event.attributes['junjo.node.id'] == mermaidNodeId,
        )
        const nodeFirstStateEvent = nodeStateEvents[0] ?? null

        if (nodeFirstStateEvent) {
          // Set the active SetState event to the first event in this node
          setActiveNodeSetStateEvent(nodeFirstStateEvent)

          // Scroll to the state event
          setScrollToPatchId(nodeFirstStateEvent.attributes.id)
        }
      } else {
        console.warn('Could not extract Mermaid Node ID from clicked element:', targetElement)
      }
    },
    [workflowStateEvents],
  )

  // --- Subflow Click Handler ---
  const handleSubflowClick = useCallback((event: MouseEvent) => {
    const targetElement = event.currentTarget as SVGGElement
    const nodeIdAttr = targetElement?.id
    const mermaidNodeId = extractMermaidNodeId(nodeIdAttr)

    if (mermaidNodeId) {
      // Handle subflow click logic here
      console.log('Subflow clicked:', mermaidNodeId)
    } else {
      console.warn('Could not extract Mermaid Node ID from clicked element:', targetElement)
    }
  }, [])

  // --- Effect for OS Theme Detection & Mermaid Theme Initialization ---
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const updateMermaidTheme = () => {
      const isDarkMode = mediaQuery.matches
      // Choose Mermaid themes for light and dark modes
      const mermaidTheme = isDarkMode ? 'dark' : 'neutral' // Or 'neutral', 'forest' etc.

      console.log(`Setting Mermaid theme based on OS: ${mermaidTheme}`)

      // Initialize Mermaid with the correct theme for subsequent renders
      mermaid.initialize({
        ...mermaidBaseConfig, // Spread your base config
        theme: mermaidTheme,
      })

      // Update state to force the rendering useEffect to re-run
      setThemeVersion((v) => v + 1)
    }

    // Set the initial theme when the component mounts
    updateMermaidTheme()

    // Add listener for OS theme changes
    mediaQuery.addEventListener('change', updateMermaidTheme)

    // Cleanup listener when the component unmounts
    return () => {
      mediaQuery.removeEventListener('change', updateMermaidTheme)
    }
  }, []) // Empty dependency array ensures this runs only once on mount/unmount

  /**
   * Rerender The Mermaid Flow Diagram on Changes
   */
  useEffect(() => {
    let nodes: NodeListOf<Element>

    // --- Click Listener Cleanup Function ---
    // This function will be returned by the effect to run on unmount or before re-run
    const cleanupEventListeners = () => {
      if (nodes) {
        // console.log('Cleaning up node click listeners...');
        nodes.forEach((node) => {
          node.removeEventListener('click', handleNodeClick as EventListener)
        })
      }
    }

    // Ensure the chart string is valid and the container exists
    if (mermaidFlowString && svgContainerRef.current) {
      const containerElement = svgContainerRef.current
      containerElement.innerHTML = '' // Clear previous render

      try {
        // mermaid.render() generates SVG code as a string
        const svgId = `mermaid-svg-${mermaidUniqueId}` // Unique ID for the SVG itself

        console.log('Re-rendering mermaid diagram.')
        // mermaid.render will use the theme set by mermaid.initialize()
        mermaid
          .render(svgId, mermaidFlowString)
          .then(({ svg, bindFunctions }) => {
            if (svgContainerRef.current) {
              // Inject the rendered SVG into the container
              svgContainerRef.current.innerHTML = svg

              // --- Attach Click Listeners ---
              nodes = containerElement.querySelectorAll('.node') // Find nodes within the new SVG
              // console.log(`Found ${nodes.length} nodes to attach listeners.`);
              nodes.forEach((node) => {
                console.log('Adding event listeners...')

                // Add listener using the memoized handler
                node.addEventListener('click', handleNodeClick as EventListener)

                // Extract the node id
                const junjoNodeId = extractMermaidNodeId(node.id)

                // Check if this node is inside the workflow spans
                const utilizedNode = nodeSpans.find((span) => span.junjo_id === junjoNodeId)
                if (!utilizedNode) {
                  console.log('Node not utilized: ', node.id)

                  // Set not-utilized class on the node for styling
                  node.classList.add('node-not-utilized')
                }

                // Check if this is a Subflow and add a class
                const isSubflow = utilizedNode && utilizedNode.junjo_span_type === JunjoSpanType.SUBFLOW
                if (isSubflow) {
                  console.log('Subflow node found:', node.id)
                  node.classList.add('node-subflow')

                  // Add click listener to the subflow node itself
                  node.addEventListener('click', handleSubflowClick as EventListener)
                }
              })

              // Bind any interactive functions if necessary
              if (bindFunctions) {
                bindFunctions(svgContainerRef.current)
              }
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
    // Return the cleanup function
    return cleanupEventListeners

    // Re-run this effect if the diagram definition changes OR if the themeVersion changes
  }, [mermaidFlowString, mermaidUniqueId, themeVersion, workflowStateEvents]) // Added themeVersion to dependency array

  // Control active classes on the mermaidflow elements when the active patch changes
  useEffect(() => {
    // Ensure the container ref is available
    if (!svgContainerRef.current) {
      console.warn('Mermaid container ref not available yet.')
      return
    }

    const containerElement = svgContainerRef.current

    // --- Remove active class efficiently ---
    // Find the currently active node *within this container* and remove the class
    const previousActive = containerElement.querySelector('.mermaid-node-active')
    if (previousActive) {
      previousActive.classList.remove('mermaid-node-active')
    }

    // --- Add active class to the new active node ---
    if (activeSetStateEventNodeId) {
      // Construct the base ID prefix we expect
      const baseTargetId = `flowchart-${activeSetStateEventNodeId}`
      console.log('Attempting to find active node starting with ID:', baseTargetId)

      // Use querySelector with an attribute "starts with" selector [id^=...]
      // Query within the specific containerElement for better scoping
      // Use CSS.escape for robustness with potential special characters in IDs
      const activeNode = containerElement.querySelector(`[id^="${CSS.escape(baseTargetId)}"]`)
      // Alternative selector if sometimes there's no index:
      // const activeNode = containerElement.querySelector(`[id^="${CSS.escape(baseTargetId)}"], #${CSS.escape(baseTargetId)}`);

      if (activeNode && activeNode.classList.contains('node')) {
        // Extra check that it's a node group
        console.log('Found activeNode element:', activeNode.id)
        activeNode.classList.add('mermaid-node-active')
      } else {
        console.warn('Could not find node element starting with ID:', baseTargetId)
      }
    }
    // Dependencies: Ensure all variables used inside are listed, including the container ref's existence indirectly
  }, [activeSetStateEventNodeId, svgContainerRef])

  console.log('Rendering mermaid diagram string:\n', mermaidFlowString)

  // Render the container div where the SVG will be placed
  return <div ref={svgContainerRef} className={'mermaid-container'} id={containerId} />
}
