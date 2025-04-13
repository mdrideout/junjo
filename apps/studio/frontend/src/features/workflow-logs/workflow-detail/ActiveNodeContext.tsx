import React, { createContext, useContext, useState, Dispatch, SetStateAction } from 'react'
import { JunjoSetStateEvent, OtelSpan } from '../../otel/store/schemas'

interface ActiveNodeContextType {
  activeSpan: OtelSpan | null
  setActiveSpan: Dispatch<SetStateAction<OtelSpan | null>>
  activeSetStateEvent: JunjoSetStateEvent | null
  setActiveSetStateEvent: Dispatch<SetStateAction<JunjoSetStateEvent | null>>
  scrollToSpanId: string | null
  setScrollToSpanId: Dispatch<SetStateAction<string | null>>
}

const ActiveNodeContext = createContext<ActiveNodeContextType | undefined>(undefined)

export const useActiveNodeContext = () => {
  const context = useContext(ActiveNodeContext)
  if (!context) {
    throw new Error('useActiveNodeContext must be used within an ActiveNodeProvider')
  }
  return context
}

interface ActiveNodeProviderProps {
  children: React.ReactNode
}

export const ActiveNodeProvider: React.FC<ActiveNodeProviderProps> = ({ children }) => {
  const [activeSetStateEvent, setActiveSetStateEvent] = useState<JunjoSetStateEvent | null>(null)
  const [scrollToSpanId, setScrollToSpanId] = useState<string | null>(null)
  const [activeSpan, setActiveSpan] = useState<OtelSpan | null>(null)

  return (
    <ActiveNodeContext.Provider
      value={{
        activeSetStateEvent,
        setActiveSetStateEvent,
        scrollToSpanId,
        setScrollToSpanId,
        activeSpan,
        setActiveSpan,
      }}
    >
      {children}
    </ActiveNodeContext.Provider>
  )
}
