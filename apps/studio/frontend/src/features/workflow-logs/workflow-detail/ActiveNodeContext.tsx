import React, { createContext, useContext, useState, Dispatch, SetStateAction } from 'react'
import { NodeSetStateEvent } from '../../otel/store/schemas'

interface ActiveNodeContextType {
  activeNodeSetStateEvent: NodeSetStateEvent | null
  setActiveNodeSetStateEvent: Dispatch<SetStateAction<NodeSetStateEvent | null>>
  scrollToPatchId: string | null
  setScrollToPatchId: Dispatch<SetStateAction<string | null>>
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
  const [activeNodeSetStateEvent, setActiveNodeSetStateEvent] = useState<NodeSetStateEvent | null>(null)
  const [scrollToPatchId, setScrollToPatchId] = useState<string | null>(null)

  return (
    <ActiveNodeContext.Provider
      value={{ activeNodeSetStateEvent, setActiveNodeSetStateEvent, scrollToPatchId, setScrollToPatchId }}
    >
      {children}
    </ActiveNodeContext.Provider>
  )
}
