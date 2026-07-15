import type { ReactNode } from 'react'
import {
  WorkflowDetailRouteContext,
  type WorkflowDetailRouteIdentity,
} from './workflow-detail-route-context'

export function WorkflowDetailRouteProvider({
  identity,
  children,
}: {
  identity: WorkflowDetailRouteIdentity
  children: ReactNode
}) {
  return (
    <WorkflowDetailRouteContext.Provider value={identity}>
      {children}
    </WorkflowDetailRouteContext.Provider>
  )
}
