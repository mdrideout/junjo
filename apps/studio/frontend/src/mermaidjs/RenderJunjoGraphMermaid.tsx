import { useEffect, useRef, useState } from 'react' // Import useState
import { JunjoGraph } from '../junjo-graph/junjo-graph'
import mermaid from 'mermaid'
import { nanoid } from '@reduxjs/toolkit'

interface RenderJunjoGraphMermaidProps {
  graph: JunjoGraph
}

// Base Mermaid configuration - customize as needed
// startOnLoad: false is important when using mermaid.render() manually
const mermaidBaseConfig = {
  startOnLoad: false,
  // securityLevel: 'loose', // Example other config
}

export default function RenderJunjoGraphMermaid(props: RenderJunjoGraphMermaidProps) {
  const { graph } = props
  const mermaidFlowString = graph.toMermaid()

  // Generate a unique ID for the container div and SVG
  const uniqueId = nanoid()
  const containerId = `mermaid-container-${uniqueId}`
  const svgContainerRef = useRef<HTMLDivElement>(null)
  // State to trigger re-render when the OS theme changes
  const [themeVersion, setThemeVersion] = useState(0)

  // --- Effect for OS Theme Detection & Mermaid Theme Initialization ---
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    const updateMermaidTheme = () => {
      const isDarkMode = mediaQuery.matches
      // Choose Mermaid themes for light and dark modes
      const mermaidTheme = isDarkMode ? 'dark' : 'default' // Or 'neutral', 'forest' etc.

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
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', updateMermaidTheme)
    } else {
      mediaQuery.addListener(updateMermaidTheme) // Fallback for older browsers
    }

    // Cleanup listener when the component unmounts
    return () => {
      if (mediaQuery.removeEventListener) {
        mediaQuery.removeEventListener('change', updateMermaidTheme)
      } else {
        mediaQuery.removeListener(updateMermaidTheme)
      }
    }
  }, []) // Empty dependency array ensures this runs only once on mount/unmount

  // --- Effect for Rendering the Mermaid Diagram ---
  useEffect(() => {
    // Ensure the chart string is valid and the container exists
    if (mermaidFlowString && svgContainerRef.current) {
      // Clear previous render (important for updates)
      svgContainerRef.current.innerHTML = ''

      try {
        // mermaid.render() generates SVG code as a string
        const svgId = `mermaid-svg-${uniqueId}` // Unique ID for the SVG itself

        // mermaid.render will use the theme set by mermaid.initialize()
        mermaid
          .render(svgId, mermaidFlowString)
          .then(({ svg, bindFunctions }) => {
            if (svgContainerRef.current) {
              // Inject the rendered SVG into the container
              svgContainerRef.current.innerHTML = svg
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
    // Re-run this effect if the diagram definition changes OR if the themeVersion changes
  }, [mermaidFlowString, uniqueId, themeVersion]) // Added themeVersion to dependency array

  // Render the container div where the SVG will be placed
  return <div ref={svgContainerRef} id={containerId} />
}
