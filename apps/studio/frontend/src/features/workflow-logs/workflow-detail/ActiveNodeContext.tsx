import React, { createContext, useContext, useState, Dispatch, SetStateAction } from 'react'
import { JunjoSetStateEvent, OtelSpan } from '../../otel/store/schemas'

interface ActiveSpanContextType {
  activeSpan: OtelSpan | null
  setActiveSpan: Dispatch<SetStateAction<OtelSpan | null>>
  activeSetStateEvent: JunjoSetStateEvent | null
  setActiveSetStateEvent: Dispatch<SetStateAction<JunjoSetStateEvent | null>>
  scrollToSpanId: string | null
  setScrollToSpanId: Dispatch<SetStateAction<string | null>>
}

const ActiveNodeContext = createContext<ActiveSpanContextType | undefined>(undefined)

export const useActiveSpanContext = () => {
  const context = useContext(ActiveNodeContext)
  if (!context) {
    throw new Error('useActiveSpanContext must be used within an ActiveSpanProvider')
  }
  return context
}

interface ActiveSpanProviderProps {
  children: React.ReactNode
}

export const ActiveSpanProvider: React.FC<ActiveSpanProviderProps> = ({ children }) => {
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
