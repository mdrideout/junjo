import React, { useEffect, createContext } from 'react'
import mermaid, { MermaidConfig } from 'mermaid'

// Create a context for mermaid-related functionality
export const MermaidContext = createContext({
  // You can add functions here if needed, like forceRerender
})

// Define the base config to avoid repetition
const getMermaidConfig = (theme: 'dark' | 'neutral'): MermaidConfig => ({
  startOnLoad: false,
  theme: theme,
  flowchart: {
    htmlLabels: true,
    curve: 'linear',
  },
  // Optional other global config settings
})

export function MermaidProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // helper to init with current prefers‑color‑scheme
    const applyTheme = () => {
      // console.log('Applying mermaid theme: ', window.matchMedia('(prefers-color-scheme: dark)').matches)
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      mermaid.initialize(getMermaidConfig(isDark ? 'dark' : 'neutral'))
    }

    applyTheme() // initial init

    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', applyTheme)
    return () => {
      mq.removeEventListener('change', applyTheme)
    }
  }, []) // ← run once

  return <MermaidContext.Provider value={{}}>{children}</MermaidContext.Provider>
}
