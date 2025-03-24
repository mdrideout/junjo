import React, { createContext, useContext, useState, Dispatch, SetStateAction } from 'react'

export type ActiveStatePatch = {
  nodeSpanID: string
  patchID: string
}

interface ActiveNodeContextType {
  activeStatePatch: ActiveStatePatch | null
  setActiveStatePatch: Dispatch<SetStateAction<ActiveStatePatch | null>>
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
  const [activeStatePatch, setActiveStatePatch] = useState<ActiveStatePatch | null>(null)

  return (
    <ActiveNodeContext.Provider value={{ activeStatePatch, setActiveStatePatch }}>
      {children}
    </ActiveNodeContext.Provider>
  )
}
