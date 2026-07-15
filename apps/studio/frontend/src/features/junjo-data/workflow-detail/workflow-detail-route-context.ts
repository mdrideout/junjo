import { createContext, useContext } from 'react'
import { useParams } from 'react-router'

export interface WorkflowDetailRouteIdentity {
  serviceName: string
  traceId: string
  workflowSpanId: string
  spanId?: string
}

export const WorkflowDetailRouteContext = createContext<WorkflowDetailRouteIdentity | null>(null)

export function useWorkflowDetailRoute(): Partial<WorkflowDetailRouteIdentity> {
  const identity = useContext(WorkflowDetailRouteContext)
  const routeParameters = useParams<{
    serviceName?: string
    traceId?: string
    workflowSpanId?: string
    spanId?: string
  }>()
  return identity ?? routeParameters
}
